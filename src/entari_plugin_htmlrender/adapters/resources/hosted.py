"""Lifecycle-owned storage and HTTP serving for published assets.

``HostedAssetStore`` is the service-owned store for every asset htmlrender
publishes to the executing browser: it holds the temporary directory, the
per-asset guard registry, the capacity ledger, and the shutdown hook. The
Entari host owns an aiohttp server at ``/_htmlrender/assets/``; publishers
only interact through their
own :class:`HostedAssetNamespace` handle and can never touch another
runtime's assets or another plugin's routes.

Capacity is a hard budget: entries and bytes are reserved before a file is
written, only lease-free assets are evictable (their files are deleted), and
a store whose remaining assets are all leased raises a stable capacity
error. TTLs govern reuse freshness in the publisher, never capacity.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping  # noqa: TC003
from dataclasses import dataclass, field
import mimetypes
from pathlib import Path
import shutil
import tempfile
from typing import TYPE_CHECKING, final
from urllib.parse import quote
import uuid

import anyio
from anyio.to_thread import run_sync
from exceptiongroup import BaseExceptionGroup

from entari_plugin_htmlrender._logging import logger
from entari_plugin_htmlrender.rendering.errors import ProviderLifecycleError
from entari_plugin_htmlrender.resources.errors import (
    ResourcePublishError,
    ResourceTooLargeError,
)
from entari_plugin_htmlrender.resources.headers import (
    RequestHeaderConflict,
    combine_request_capabilities,
)
from entari_plugin_htmlrender.resources.models import PublicationLeaseId  # noqa: TC001

if TYPE_CHECKING:
    from aiohttp.web import Request, StreamResponse
    from aiohttp.web_runner import AppRunner

HOSTED_ASSET_MOUNT = "/_htmlrender/assets"


class HostedAssetCapacityError(ResourcePublishError):
    """The hosted asset budget is exhausted by lease-pinned assets."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            reference=None,
            operation="publish",
        )


@dataclass(slots=True)
class _HostedAsset:
    namespace: str
    name: str
    path: Path
    size: int
    media_type: str | None
    headers: Mapping[str, str]
    leases: set[PublicationLeaseId] = field(default_factory=set)


@final
class HostedAssetStore:
    """Content-addressed, capacity-bounded storage behind the fixed mount."""

    def __init__(self, *, max_entries: int, max_bytes: int) -> None:
        if max_entries <= 0 or max_bytes <= 0:
            raise ValueError("Hosted asset capacity limits must be positive.")
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._directory: Path | None = None
        self._entries: OrderedDict[tuple[str, str], _HostedAsset] = OrderedDict()
        self._resident_bytes = 0
        self._reserved_entries = 0
        self._reserved_bytes = 0
        self._lock = anyio.Lock()
        self._closed = False

    @property
    def limits(self) -> tuple[int, int]:
        return self._max_entries, self._max_bytes

    async def startup(self) -> None:
        """Create transient storage during the owning lifecycle's startup."""
        async with self._lock:
            if self._directory is not None:
                return
            if self._closed:
                raise ProviderLifecycleError(
                    "The hosted asset store is closed.",
                    provider_id=None,
                    operation="startup",
                )
            self._directory = await run_sync(_create_temp_directory)

    def open_namespace(
        self,
        *,
        headers: Mapping[str, str],
        public_base_url: str,
    ) -> HostedAssetNamespace:
        """Hand one runtime publisher its private namespace handle."""
        return HostedAssetNamespace(
            store=self,
            namespace=uuid.uuid4().hex,
            headers=dict(headers),
            public_base_url=public_base_url,
        )

    def lookup(self, namespace: str, name: str) -> _HostedAsset | None:
        """Resolve one asset for the route handler; ``None`` means 404."""
        return self._entries.get((namespace, name))

    def _evict_locked(self, incoming_bytes: int) -> list[Path]:
        """Reserve room for one incoming asset, returning files to delete."""
        if incoming_bytes > self._max_bytes:
            raise ResourceTooLargeError(
                "Hosted asset exceeds the configured "
                f"{self._max_bytes}-byte publish budget.",
                reference=None,
                operation="publish",
                actual_size=incoming_bytes,
                maximum_size=self._max_bytes,
            )
        removed: list[Path] = []

        def over_budget() -> bool:
            entries = (
                len(self._entries) + self._reserved_entries + 1 - self._max_entries
            )
            resident = (
                self._resident_bytes
                + self._reserved_bytes
                + incoming_bytes
                - self._max_bytes
            )
            return entries > 0 or resident > 0

        while over_budget():
            victim_key = next(
                (key for key, asset in self._entries.items() if not asset.leases),
                None,
            )
            if victim_key is None:
                raise HostedAssetCapacityError(
                    "Hosted asset capacity is exhausted and every resident "
                    "asset is pinned by an active render lease."
                )
            victim = self._entries.pop(victim_key)
            self._resident_bytes -= victim.size
            removed.append(victim.path)
        return removed

    async def put(
        self,
        namespace: str,
        name: str,
        data: bytes,
        *,
        headers: Mapping[str, str],
        lease_ids: Iterable[PublicationLeaseId] = (),
    ) -> None:
        """Admit one content-addressed asset under the capacity budget.

        Callers singleflight per ``(namespace, name)``; a repeated put for a
        resident asset only attaches leases and refreshes recency.
        """
        key = (namespace, name)
        size = len(data)
        async with self._lock:
            if self._closed:
                raise ResourcePublishError(
                    "The hosted asset store is closed.",
                    reference=key,
                    operation="publish",
                )
            directory = self._directory
            if directory is None:
                raise ResourcePublishError(
                    "The hosted asset store has not been started.",
                    reference=key,
                    operation="publish",
                )
            path = _contained_asset_path(directory, namespace, name)
            existing = self._entries.get(key)
            if existing is not None:
                try:
                    combine_request_capabilities(existing.headers, headers)
                except RequestHeaderConflict as error:
                    raise ResourcePublishError(
                        "Conflicting request capabilities for one hosted "
                        "asset identity.",
                        reference=key,
                        operation="publish",
                        source=error,
                    ) from error
                existing.leases.update(lease_ids)
                self._entries.move_to_end(key)
                return
            removed = self._evict_locked(size)
            self._reserved_entries += 1
            self._reserved_bytes += size
        try:
            for stale in removed:
                await run_sync(_unlink_quietly, stale)
            await run_sync(_write_asset_file, path, data)
        except BaseException:
            async with self._lock:
                self._reserved_entries -= 1
                self._reserved_bytes -= size
            raise
        async with self._lock:
            self._reserved_entries -= 1
            self._reserved_bytes -= size
            if self._closed:
                await run_sync(_unlink_quietly, path)
                raise ResourcePublishError(
                    "The hosted asset store is closed.",
                    reference=key,
                    operation="publish",
                )
            self._entries[key] = _HostedAsset(
                namespace=namespace,
                name=name,
                path=path,
                size=size,
                media_type=mimetypes.guess_type(name)[0],
                headers=dict(headers),
                leases=set(lease_ids),
            )
            self._resident_bytes += size
            self._entries.move_to_end(key)

    async def attach(
        self,
        namespace: str,
        name: str,
        lease_id: PublicationLeaseId,
    ) -> bool:
        """Pin a resident asset to a lease; ``False`` when it was evicted."""
        async with self._lock:
            asset = self._entries.get((namespace, name))
            if asset is None:
                return False
            asset.leases.add(lease_id)
            self._entries.move_to_end((namespace, name))
            return True

    async def touch(self, namespace: str, name: str) -> bool:
        """Refresh recency of a resident asset; ``False`` when evicted."""
        async with self._lock:
            if (namespace, name) not in self._entries:
                return False
            self._entries.move_to_end((namespace, name))
            return True

    async def release(
        self,
        namespace: str,
        lease_id: PublicationLeaseId,
    ) -> None:
        async with self._lock:
            for asset in self._entries.values():
                if asset.namespace == namespace:
                    asset.leases.discard(lease_id)

    async def _drop_namespace(self, namespace: str, *, keep_leased: bool) -> None:
        async with self._lock:
            victims = [
                key
                for key, asset in self._entries.items()
                if asset.namespace == namespace and not (keep_leased and asset.leases)
            ]
            removed: list[Path] = []
            for key in victims:
                asset = self._entries.pop(key)
                self._resident_bytes -= asset.size
                removed.append(asset.path)
        for stale in removed:
            await run_sync(_unlink_quietly, stale)

    async def clear_namespace(self, namespace: str) -> None:
        """Drop the namespace's lease-free assets and delete their files."""
        await self._drop_namespace(namespace, keep_leased=True)

    async def close_namespace(self, namespace: str) -> None:
        """Release everything one runtime publisher ever published."""
        await self._drop_namespace(namespace, keep_leased=False)

    async def aclose(self) -> None:
        """Driver-shutdown hook: drop every asset and the temp directory."""
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            self._entries.clear()
            self._resident_bytes = 0
            directory = self._directory
            self._directory = None
        if directory is not None:
            await run_sync(_remove_tree_quietly, directory)


@final
class HostedAssetNamespace:
    """One runtime publisher's private window into the host store."""

    def __init__(
        self,
        *,
        store: HostedAssetStore,
        namespace: str,
        headers: Mapping[str, str],
        public_base_url: str,
    ) -> None:
        self._store = store
        self._namespace = namespace
        self._headers = dict(headers)
        self._base_url = public_base_url

    def url_for(self, name: str) -> str:
        return (
            f"{self._base_url}{quote(self._namespace, safe='')}/{quote(name, safe='')}"
        )

    async def put(
        self,
        name: str,
        data: bytes,
        *,
        lease_ids: Iterable[PublicationLeaseId] = (),
    ) -> str:
        await self._store.put(
            self._namespace,
            name,
            data,
            headers=self._headers,
            lease_ids=lease_ids,
        )
        return self.url_for(name)

    async def attach(self, name: str, lease_id: PublicationLeaseId) -> bool:
        return await self._store.attach(self._namespace, name, lease_id)

    async def touch(self, name: str) -> bool:
        return await self._store.touch(self._namespace, name)

    async def release(self, lease_id: PublicationLeaseId) -> None:
        await self._store.release(self._namespace, lease_id)

    async def clear(self) -> None:
        await self._store.clear_namespace(self._namespace)

    async def aclose(self) -> None:
        await self._store.close_namespace(self._namespace)


def _write_asset_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _contained_asset_path(directory: Path, namespace: str, name: str) -> Path:
    if (
        not isinstance(namespace, str)
        or not isinstance(name, str)
        or not namespace
        or not name
        or "/" in namespace
        or "\\" in namespace
        or "/" in name
        or "\\" in name
        or namespace in {".", ".."}
        or name in {".", ".."}
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
        or any(ord(character) < 32 or ord(character) == 127 for character in namespace)
    ):
        raise ResourcePublishError(
            "Hosted asset identity must contain single path segments.",
            reference=(namespace, name),
            operation="publish",
        )
    try:
        store_root = directory.resolve()
        namespace_root = (store_root / namespace).resolve()
        path = (namespace_root / name).resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise ResourcePublishError(
            "Hosted asset path could not be validated.",
            reference=(namespace, name),
            operation="publish",
            source=error,
        ) from error
    if namespace_root.parent != store_root or path.parent != namespace_root:
        raise ResourcePublishError(
            "Hosted asset path escapes its publication namespace.",
            reference=(namespace, name),
            operation="publish",
        )
    return path


def _create_temp_directory() -> Path:
    return Path(tempfile.mkdtemp(prefix="htmlrender-assets-"))


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete a hosted asset file.")


def _remove_tree_quietly(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


@final
class HostedAssetHttpServer:
    """Explicitly owned aiohttp server for one hosted-asset store."""

    def __init__(
        self,
        store: HostedAssetStore,
        *,
        bind_host: str,
        bind_port: int,
    ) -> None:
        if not bind_host.strip():
            raise ValueError("Hosted asset bind host must not be empty.")
        if not 0 <= bind_port <= 65535:
            raise ValueError("Hosted asset bind port must be between 0 and 65535.")
        self._store = store
        self._bind_host = bind_host
        self._bind_port = bind_port
        self._runner: AppRunner | None = None
        self._lock = anyio.Lock()
        self._closed = False

    @property
    def store(self) -> HostedAssetStore:
        return self._store

    async def startup(self) -> None:
        async with self._lock:
            if self._runner is not None:
                return
            if self._closed:
                raise ProviderLifecycleError(
                    "The hosted asset server is closed.",
                    provider_id=None,
                    operation="startup",
                )
            await self._store.startup()
            try:
                from aiohttp import web  # noqa: PLC0415
            except ImportError as error:
                raise ProviderLifecycleError(
                    "Filehost serving requires the `filehost` extra.",
                    provider_id=None,
                    operation="startup",
                    source=error,
                ) from error

            app = web.Application()

            async def serve(request: Request) -> StreamResponse:
                asset = self._store.lookup(
                    request.match_info["namespace"],
                    request.match_info["name"],
                )
                if asset is None:
                    return web.Response(text="Not Found", status=404)
                for header, expected in asset.headers.items():
                    if request.headers.get(header) != expected:
                        return web.Response(text="Forbidden", status=403)
                response = web.FileResponse(
                    asset.path,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "public, max-age=31536000, immutable",
                    },
                )
                response.content_type = asset.media_type or "application/octet-stream"
                return response

            app.router.add_get(
                HOSTED_ASSET_MOUNT + "/{namespace}/{name}",
                serve,
            )
            runner = web.AppRunner(app)
            try:
                await runner.setup()
                site = web.TCPSite(runner, self._bind_host, self._bind_port)
                await site.start()
            except BaseException as error:
                try:
                    await runner.cleanup()
                except BaseException as cleanup_error:
                    raise BaseExceptionGroup(
                        "Hosted asset server startup and rollback failed.",
                        [error, cleanup_error],
                    ) from error
                raise
            self._runner = runner
            logger.info(
                "Hosted asset server listening on %s:%d%s/.",
                self._bind_host,
                self._bind_port,
                HOSTED_ASSET_MOUNT,
            )

    async def aclose(self) -> None:
        async with self._lock:
            runner = self._runner
            errors: list[BaseException] = []
            if runner is not None:
                try:
                    await runner.cleanup()
                except BaseException as error:
                    errors.append(error)
                else:
                    self._runner = None
            try:
                await self._store.aclose()
            except BaseException as error:
                errors.append(error)
            if not errors:
                self._closed = True
                return
            if len(errors) == 1:
                raise errors[0]
            raise BaseExceptionGroup("Hosted asset server shutdown failed.", errors)


__all__ = [
    "HOSTED_ASSET_MOUNT",
    "HostedAssetCapacityError",
    "HostedAssetHttpServer",
    "HostedAssetNamespace",
    "HostedAssetStore",
]
