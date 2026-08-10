from dataclasses import dataclass, field
from hashlib import sha256
from importlib import import_module
from pathlib import Path
import time
from types import MappingProxyType
from typing import TYPE_CHECKING
import uuid

import anyio

from entari_plugin_htmlrender._logging import logger
from entari_plugin_htmlrender.rendering.errors import ProviderLifecycleError
from entari_plugin_htmlrender.resources._publication import (
    normalize_publication_suffix,
)
from entari_plugin_htmlrender.resources.config import AssetPublisherSettings
from entari_plugin_htmlrender.resources.errors import (
    ResourceError,
    ResourcePublishError,
    ResourceTooLargeError,
)
from entari_plugin_htmlrender.resources.models import (
    InlineResource,
    PublicationLeaseId,
    PublishedResource,
    ResourceContent,
)
from entari_plugin_htmlrender.resources.observation import CacheObserver
from entari_plugin_htmlrender.resources.ports import LocalAccessPolicy, WorkerExecutor

from .hosted import HostedAssetNamespace, HostedAssetStore

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(slots=True)
class _Entry:
    url: str
    expires_at: float
    leases: set[PublicationLeaseId]


@dataclass(slots=True)
class _Inflight:
    event: anyio.Event
    epoch: int
    url: str | None = None
    error: BaseException | None = None
    leases: set[PublicationLeaseId] = field(default_factory=set)


def _read_consistent(path: Path, max_resource_bytes: int) -> tuple[bytes, str]:
    resolved = path.expanduser().resolve()
    for _ in range(3):
        before = resolved.stat()
        if max_resource_bytes > 0 and before.st_size > max_resource_bytes:
            raise ResourceTooLargeError(
                f"Resource {resolved} exceeds the configured "
                f"{max_resource_bytes}-byte publish limit.",
                reference=path,
                operation="publish",
                actual_size=before.st_size,
                maximum_size=max_resource_bytes,
            )
        with resolved.open("rb") as stream:
            data = (
                stream.read()
                if max_resource_bytes == 0
                else stream.read(max_resource_bytes + 1)
            )
        if max_resource_bytes > 0 and len(data) > max_resource_bytes:
            raise ResourceTooLargeError(
                f"Resource {resolved} exceeds the configured "
                f"{max_resource_bytes}-byte publish limit.",
                reference=path,
                operation="publish",
                actual_size=len(data),
                maximum_size=max_resource_bytes,
            )
        after = resolved.stat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) and len(data) == after.st_size:
            return data, resolved.suffix
    raise RuntimeError(f"File changed repeatedly while publishing: {resolved}")


def _prewarm_candidates(
    roots: tuple[Path, ...],
    extensions: frozenset[str],
    limit: int,
) -> tuple[Path, ...]:
    candidates: list[Path] = []
    for configured in roots:
        root = configured.expanduser().resolve()
        paths = (root,) if root.is_file() else root.rglob("*") if root.is_dir() else ()
        for path in paths:
            if not path.is_file() or (
                extensions and path.suffix.lower() not in extensions
            ):
                continue
            candidates.append(path)
            if len(candidates) >= limit:
                return tuple(candidates)
    return tuple(candidates)


def _request_guard_values(settings: AssetPublisherSettings) -> tuple[str, str]:
    header_name = settings.request_header_name.strip()
    if settings.request_header_value:
        return header_name, settings.request_header_value
    try:
        machineid = import_module("machineid")
        identity = str(machineid.id()).strip()
    except Exception:
        identity = f"mac:{uuid.getnode():012x}"
    value = sha256(f"{settings.request_header_salt}:{identity}".encode()).hexdigest()
    return header_name, value


class FilehostAssetPublisher:
    """Instance-owned, content-addressed publisher over the hosted store.

    Publishing goes exclusively through this runtime's
    :class:`HostedAssetNamespace`; the service-owned store owns files,
    capacity, and the request-guard registry, while this publisher owns
    reuse freshness (TTL), leases, and singleflight per content digest.
    """

    def __init__(
        self,
        *,
        settings: AssetPublisherSettings,
        observer: CacheObserver,
        worker: WorkerExecutor,
        local_access: LocalAccessPolicy,
        store: HostedAssetStore,
    ) -> None:
        self._settings = settings
        self._observer = observer
        self._worker = worker
        self._local_access = local_access
        self._store = store
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._inflight: dict[tuple[str, str], _Inflight] = {}
        self._epoch = 0
        self._lock = anyio.Lock()
        self._closed = False
        self._drained = anyio.Event()
        self._drained.set()
        self._header_name, self._header_value = _request_guard_values(settings)
        self._request_headers: Mapping[str, str] = MappingProxyType(
            {self._header_name: self._header_value}
        )
        self._namespace: HostedAssetNamespace | None = None

    def create_lease(self) -> PublicationLeaseId:
        return PublicationLeaseId(f"lease:{uuid.uuid4().hex}")

    def _published(self, url: str) -> PublishedResource:
        return PublishedResource(url=url, request_headers=self._request_headers)

    def _attach_namespace(self) -> HostedAssetNamespace:
        """Bind this publisher to its private namespace in the host store."""
        if self._namespace is not None:
            return self._namespace
        if self._settings.public_base_url is None:
            raise ProviderLifecycleError(
                "The filehost transport requires `resources.filehost.public_base_url`.",
                provider_id=None,
                operation="startup",
            )
        self._namespace = self._store.open_namespace(
            headers=self._request_headers,
            public_base_url=self._settings.public_base_url,
        )
        return self._namespace

    async def startup(self) -> None:
        async with self._lock:
            if self._closed:
                raise ProviderLifecycleError(
                    "The filehost publisher is already closed.",
                    provider_id=None,
                    operation="startup",
                )
        self._attach_namespace()
        try:
            await self._prewarm()
        except BaseException:
            # The composition root only rolls back completed steps; partial
            # prewarm state is this step's own to drop before re-raising.
            with anyio.CancelScope(shield=True):
                await self.clear()
            raise

    async def _prewarm(self) -> None:
        if not self._settings.prewarm_enabled or self._settings.prewarm_max_files == 0:
            return
        extensions = frozenset(
            value.lower() if value.startswith(".") else f".{value.lower()}"
            for value in self._settings.prewarm_extensions
            if value
        )
        candidates = await self._worker.run_sync(
            _prewarm_candidates,
            self._settings.prewarm_paths,
            extensions,
            self._settings.prewarm_max_files,
        )
        for path in candidates:
            try:
                authorized = self._local_access.authorize(
                    path,
                )
                data, suffix = await self._worker.run_sync(
                    _read_consistent,
                    authorized,
                    self._settings.max_resource_bytes,
                )
                await self.publish(InlineResource(data), suffix=suffix or None)
            except Exception as error:  # noqa: PERF203 -- optional files are isolated
                logger.warning(
                    "Could not prewarm a filehost resource: %s",
                    type(error).__name__,
                )

    async def aclose(self) -> None:
        async with self._lock:
            self._closed = True
            drained = self._drained
        with anyio.move_on_after(30, shield=True) as scope:
            await drained.wait()
        if scope.cancel_called:
            raise ProviderLifecycleError(
                "Timed out waiting for in-flight filehost publishes to finish.",
                provider_id=None,
                operation="aclose",
                retryable=True,
            )
        async with self._lock:
            self._entries.clear()
        namespace = self._namespace
        if namespace is not None:
            with anyio.CancelScope(shield=True):
                await namespace.aclose()

    async def clear(self) -> None:
        """Clear published URL mappings without terminating the instance."""
        async with self._lock:
            self._epoch += 1
            self._entries.clear()
        namespace = self._namespace
        if namespace is not None:
            await namespace.clear()

    async def _upload(
        self,
        key: tuple[str, str],
        data: bytes,
        lease_ids: set[PublicationLeaseId],
    ) -> str:
        digest, suffix = key
        return await self._attach_namespace().put(
            f"{digest}{suffix}",
            data,
            lease_ids=lease_ids,
        )

    def _record(self, events: dict[str, int]) -> None:
        try:
            self._observer.record("filehost", events, len(self._entries))
        except Exception:
            return

    async def publish(
        self,
        content: ResourceContent | InlineResource,
        *,
        lease_id: PublicationLeaseId | None = None,
        suffix: str | None = None,
    ) -> PublishedResource:
        data = content.data
        if (
            self._settings.max_resource_bytes > 0
            and len(data) > self._settings.max_resource_bytes
        ):
            raise ResourceTooLargeError(
                "Resource exceeds the configured "
                f"{self._settings.max_resource_bytes}-byte publish limit.",
                reference=content,
                operation="publish",
                actual_size=len(data),
                maximum_size=self._settings.max_resource_bytes,
            )
        normalized_suffix = normalize_publication_suffix(suffix) or ""
        key = (sha256(data).hexdigest(), normalized_suffix)
        now = time.monotonic()
        async with self._lock:
            if self._closed:
                raise ResourcePublishError(
                    "The filehost publisher is closed.",
                    reference=content,
                    operation="publish",
                )
            expired = [
                cache_key
                for cache_key, entry in self._entries.items()
                if not entry.leases and entry.expires_at <= now
            ]
            for cache_key in expired:
                self._entries.pop(cache_key, None)
            entry = self._entries.get(key)
            hit_url: str | None = None
            if entry is not None:
                if lease_id is not None:
                    entry.leases.add(lease_id)
                hit_url = entry.url
        if hit_url is not None:
            # The URL mapping must not outlive the bytes: confirm the store
            # still holds the asset (pinning it to the lease) before reuse.
            if await self._confirm_hosted(key, lease_id):
                self._record({"hit": 1})
                return self._published(hit_url)
            async with self._lock:
                current = self._entries.get(key)
                if current is not None and current.url == hit_url:
                    self._entries.pop(key, None)

        async with self._lock:
            if self._closed:
                raise ResourcePublishError(
                    "The filehost publisher is closed.",
                    reference=content,
                    operation="publish",
                )
            inflight = self._inflight.get(key)
            owner = inflight is None
            if inflight is None:
                inflight = _Inflight(anyio.Event(), self._epoch)
                self._inflight[key] = inflight
                if len(self._inflight) == 1:
                    self._drained = anyio.Event()
            if lease_id is not None:
                inflight.leases.add(lease_id)
        if not owner:
            await inflight.event.wait()
            if inflight.error is not None:
                raise inflight.error
            if inflight.url is None:
                return await self.publish(
                    content,
                    lease_id=lease_id,
                    suffix=normalized_suffix,
                )
            return self._published(inflight.url)
        try:
            uploaded_leases = set(inflight.leases)
            url = await self._upload(key, data, uploaded_leases)
            with anyio.CancelScope(shield=True):
                async with self._lock:
                    if inflight.epoch == self._epoch:
                        self._entries[key] = _Entry(
                            url,
                            time.monotonic() + self._settings.cache_ttl_seconds,
                            set(inflight.leases),
                        )
                    self._inflight.pop(key, None)
                    if not self._inflight:
                        self._drained.set()
                    inflight.url = url
                    inflight.event.set()
                    self._record({"miss": 1, "load": 1})
                    late_leases = set(inflight.leases) - uploaded_leases
                namespace = self._namespace
                if namespace is not None:
                    for late in late_leases:
                        await namespace.attach(f"{key[0]}{key[1]}", late)
            return self._published(url)
        except BaseException as error:
            published_error: BaseException = error
            if isinstance(error, Exception) and not isinstance(error, ResourceError):
                published_error = ResourcePublishError(
                    "Could not publish resource.",
                    reference=content,
                    operation="publish",
                    source=error,
                )
            with anyio.CancelScope(shield=True):
                async with self._lock:
                    self._inflight.pop(key, None)
                    if not self._inflight:
                        self._drained.set()
                    inflight.error = published_error
                    inflight.event.set()
            if published_error is error:
                raise
            raise published_error from error

    async def _confirm_hosted(
        self,
        key: tuple[str, str],
        lease_id: PublicationLeaseId | None,
    ) -> bool:
        """Confirm the store still holds a reused asset; pin it when leased."""
        namespace = self._namespace
        if namespace is None:
            return True
        name = f"{key[0]}{key[1]}"
        if lease_id is not None:
            return await namespace.attach(name, lease_id)
        return await namespace.touch(name)

    async def release(self, lease_id: PublicationLeaseId) -> None:
        async with self._lock:
            now = time.monotonic()
            for inflight in self._inflight.values():
                inflight.leases.discard(lease_id)
            for entry in self._entries.values():
                if lease_id in entry.leases:
                    entry.leases.remove(lease_id)
                    entry.expires_at = now + self._settings.cache_ttl_seconds
        namespace = self._namespace
        if namespace is not None:
            await namespace.release(lease_id)


__all__ = ["FilehostAssetPublisher"]
