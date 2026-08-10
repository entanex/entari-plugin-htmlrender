from __future__ import annotations

import codecs
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Generic, TypeAlias, TypeGuard, TypeVar
from urllib.parse import SplitResult, urlsplit, urlunsplit

import anyio
from exceptiongroup import BaseExceptionGroup

from entari_plugin_htmlrender._logging import logger
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    ResourceAccessDeniedError,
    ResourceError,
    ResourceFetchError,
    ResourceNotFoundError,
    ResourcePublishError,
)

from ._publication import normalize_publication_suffix
from ._traversal import ResourceTraversalBudget, VariableMaterializationPlan
from .config import (
    LocalLocalResourcePolicy,
    RemoteLocalResourcePolicy,
    ResourceMaterializationPolicy,
    ResourceStrategy,
)
from .models import (
    FileResourceRef,
    InlineResource,
    PackageResourceRef,
    PublicationLeaseId,
    PublishedResource,
    RemoteResourceRef,
    ResourceContent,
    ResourceRef,
)
from .ports import (
    AssetPublisher,
    LocalAccessPolicy,
    ResourceFetcher,
    ResourceMaterializer,
)

_WINDOWS_ABS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")

_TransportPolicy: TypeAlias = LocalLocalResourcePolicy | RemoteLocalResourcePolicy
_MaterializerSpec: TypeAlias = str | ResourceMaterializer | None
_RequestHeadersByUrl: TypeAlias = dict[str, Mapping[str, str]]
T = TypeVar("T")
_RESOURCE_REF_TYPES = (FileResourceRef, PackageResourceRef, RemoteResourceRef)


@dataclass(frozen=True, slots=True)
class _MaterializationResult(Generic[T]):
    """Internal value rewrite with exact authorization for rewritten URLs."""

    value: T
    request_headers_by_url: Mapping[str, Mapping[str, str]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        frozen_headers = {
            url: MappingProxyType(dict(headers))
            for url, headers in sorted(self.request_headers_by_url.items())
        }
        object.__setattr__(
            self,
            "request_headers_by_url",
            MappingProxyType(frozen_headers),
        )


# Derived from the enum members themselves so a value rename cannot leave a
# stale string behind.  Members whose values overlap across the two enums
# (passthrough/filehost) share identical semantics in ``_resolve_scalar``.
_EXPLICIT_POLICIES: Mapping[str, _TransportPolicy] = {
    member.value: member
    for enum_cls in (RemoteLocalResourcePolicy, LocalLocalResourcePolicy)
    for member in enum_cls
}


def _is_string_keyed_dict(value: dict[Any, Any]) -> TypeGuard[dict[str, Any]]:
    return all(isinstance(key, str) for key in value)


def _resolve_local_path(value: str | Path, *, label: str) -> Path:
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise ResourceAccessDeniedError(
            f"Could not normalize {label}.",
            reference=value,
            operation="authorize",
            source=error,
        ) from error


def _normalize_template_base(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    stripped = value if isinstance(value, Path) else value.strip()
    return _resolve_local_path(stripped, label="template base") if stripped else None


def _split_resource_url(value: str) -> SplitResult:
    try:
        return urlsplit(value)
    except ValueError as error:
        raise ResourceFetchError(
            f"Invalid resource URL {value!r}.",
            reference=value,
            operation="materialize",
            source=error,
        ) from error


def _is_explicit_url(value: str) -> bool:
    return value.lower().startswith(
        ("http://", "https://", "file://", "data:", "about:")
    )


def _is_bytes(value: object) -> TypeGuard[bytes | bytearray | BytesIO]:
    return isinstance(value, (bytes, bytearray, BytesIO))


def _is_local_string(value: str) -> bool:
    """Classify by string shape only.

    Classification must stay free of filesystem probes: touching the
    filesystem here would let arbitrary template text trigger reads and leak
    existence information before any policy check runs.  Bare names without a
    path shape stay text; callers express path intent with ``Path`` values,
    explicit ``./``-style prefixes, or concrete ``ResourceRef`` objects.
    """
    stripped = value.strip()
    if not stripped or _is_explicit_url(stripped):
        return False
    if stripped.startswith(("~", "./", "../", "/")) or _WINDOWS_ABS_PATH_RE.match(
        stripped
    ):
        return True
    return ("/" in stripped or "\\" in stripped) and " " not in stripped


def _is_scalar(value: object) -> bool:
    return (
        isinstance(value, Path)
        or _is_bytes(value)
        or (isinstance(value, str) and _is_local_string(value))
    )


def _candidate(value: str | Path, template_base: Path | None) -> Path:
    try:
        path = (
            value.expanduser()
            if isinstance(value, Path)
            else Path(value.strip()).expanduser()
        )
        if not path.is_absolute() and template_base is not None:
            path = template_base / path
        return path.resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise ResourceAccessDeniedError(
            "Could not normalize local resource path.",
            reference=value,
            operation="authorize",
            source=error,
        ) from error


class _ConflictingRequestAuthorization(ResourcePublishError):
    """A publisher reused one URL with incompatible request capabilities."""


def _record_published_resource(
    published: PublishedResource,
    request_headers_by_url: _RequestHeadersByUrl,
) -> None:
    headers = dict(published.request_headers)
    existing = request_headers_by_url.get(published.url)
    if existing is not None and dict(existing) != headers:
        raise _ConflictingRequestAuthorization(
            "The asset publisher returned conflicting authorization for one URL.",
            reference=published.url,
            operation="publish",
        )
    request_headers_by_url[published.url] = headers


class ResourceService:
    """Composition-owned resource access and internal materialization service."""

    def __init__(
        self,
        *,
        fetcher: ResourceFetcher,
        local_access: LocalAccessPolicy,
        strategy: ResourceStrategy,
        publisher: AssetPublisher | None = None,
        traversal_budget: ResourceTraversalBudget | None = None,
    ) -> None:
        budget = traversal_budget or ResourceTraversalBudget()
        self._fetcher = fetcher
        self._local_access = local_access
        self._strategy = strategy
        self._publisher = publisher
        self._traversal_budget = budget
        self._scalar_slots = anyio.Semaphore(budget.max_concurrency)

    @property
    def strategy(self) -> ResourceStrategy:
        return self._strategy

    def authorize_local(
        self,
        path: Path,
    ) -> Path:
        try:
            return self._local_access.authorize(path)
        except ResourceError:
            raise
        except (OSError, RuntimeError, ValueError) as error:
            raise ResourceAccessDeniedError(
                "Could not authorize a local resource path.",
                reference=path,
                operation="authorize",
                source=error,
            ) from error

    async def fetch(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> ResourceContent:
        if not isinstance(resource, _RESOURCE_REF_TYPES):
            raise InvalidRenderInputError(
                "fetch() requires an explicit ResourceRef locator.",
                operation="fetch",
                field="resource",
            )
        if type(refresh) is not bool:
            raise InvalidRenderInputError(
                "refresh must be a boolean.",
                operation="fetch",
                field="refresh",
            )
        try:
            return await self._fetcher.fetch(resource, refresh=refresh)
        except ResourceError:
            raise
        except Exception as error:
            raise ResourceFetchError(
                "The configured resource fetcher failed.",
                reference=resource,
                operation="fetch",
                source=error,
            ) from error

    async def fetch_bytes(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> bytes:
        return (await self.fetch(resource, refresh=refresh)).data

    async def fetch_text(
        self,
        resource: ResourceRef,
        *,
        encoding: str = "utf-8",
        errors: str = "strict",
        refresh: bool = False,
    ) -> str:
        if not isinstance(encoding, str) or not encoding:
            raise InvalidRenderInputError(
                "Resource text encoding must be a non-empty string.",
                operation="fetch_text",
                field="encoding",
            )
        if not isinstance(errors, str) or not errors:
            raise InvalidRenderInputError(
                "Resource text error handler must be a non-empty string.",
                operation="fetch_text",
                field="errors",
            )
        try:
            codecs.lookup(encoding)
        except LookupError as error:
            raise InvalidRenderInputError(
                f"Unknown resource text encoding: {encoding!r}.",
                operation="fetch_text",
                field="encoding",
                source=error,
            ) from error
        try:
            codecs.lookup_error(errors)
        except LookupError as error:
            raise InvalidRenderInputError(
                f"Unknown resource text error handler: {errors!r}.",
                operation="fetch_text",
                field="errors",
                source=error,
            ) from error
        content = await self.fetch_bytes(
            resource,
            refresh=refresh,
        )
        try:
            return content.decode(encoding, errors)
        except (LookupError, UnicodeError) as error:
            raise ResourceFetchError(
                f"Could not decode resource as {encoding}.",
                reference=resource,
                operation="fetch_text",
                source=error,
            ) from error

    @asynccontextmanager
    async def publish(
        self,
        content: ResourceContent | InlineResource,
        *,
        suffix: str | None = None,
    ) -> AsyncIterator[PublishedResource]:
        """Publish one resource for exactly the scope of the context."""

        if not isinstance(content, (ResourceContent, InlineResource)):
            raise InvalidRenderInputError(
                "publish() requires ResourceContent or InlineResource payload.",
                operation="publish",
                field="content",
            )
        normalized_suffix = normalize_publication_suffix(suffix)
        publisher = self._publisher
        if publisher is None:
            raise ResourcePublishError(
                "This composition has no resource publication transport.",
                reference=content,
                operation="publish",
            )
        lease_id = publisher.create_lease()
        primary_error: BaseException | None = None
        try:
            try:
                published = await publisher.publish(
                    content,
                    lease_id=lease_id,
                    suffix=normalized_suffix,
                )
            except ResourceError:
                raise
            except Exception as error:
                raise ResourcePublishError(
                    "Could not publish resource content.",
                    reference=content,
                    operation="publish",
                    source=error,
                ) from error
            yield published
        except BaseException as error:
            primary_error = error
        finally:
            release_error: BaseException | None = None
            try:
                with anyio.CancelScope(shield=True):
                    await publisher.release(lease_id)
            except ResourceError as error:
                release_error = error
            except Exception as error:
                release_error = ResourcePublishError(
                    "Could not release the scoped publication lease.",
                    reference=content,
                    operation="publish",
                    source=error,
                )
            except BaseException as error:
                release_error = error

            if primary_error is not None and release_error is not None:
                raise BaseExceptionGroup(
                    "Publication scope and lease release both failed.",
                    [primary_error, release_error],
                ) from None
            if primary_error is not None:
                raise primary_error
            if release_error is not None:
                raise release_error

    def _policy(
        self, materializer: _MaterializerSpec
    ) -> _TransportPolicy | ResourceMaterializer:
        if materializer is None or materializer == "auto":
            return self._strategy.local_resource_policy
        if isinstance(materializer, str):
            member = _EXPLICIT_POLICIES.get(materializer)
            if member is None:
                raise InvalidRenderInputError(
                    f"Unknown resource policy: {materializer!r}",
                    operation="materialize",
                    field="materializer",
                )
            return member
        if callable(getattr(materializer, "materialize", None)):
            return materializer
        raise InvalidRenderInputError(
            "Custom resource materializer must expose async materialize().",
            operation="materialize",
            field="materializer",
        )

    def _should_materialize(self, materializer: _MaterializerSpec = None) -> bool:
        if materializer is not None:
            return True
        return (
            self._strategy.materialization_policy
            is not ResourceMaterializationPolicy.OFF
        )

    async def _materialize_with_custom(
        self,
        materializer: ResourceMaterializer,
        value: object,
        *,
        template_base: Path | None,
    ) -> object:
        custom_value = value
        if isinstance(value, (str, Path)):
            custom_value = self.authorize_local(_candidate(value, template_base))
        return await materializer.materialize(
            custom_value,
            template_base=template_base,
        )

    async def _materialize_with_policy(
        self,
        policy: _TransportPolicy,
        value: object,
        *,
        template_base: Path | None,
        lease_id: PublicationLeaseId | None,
        request_headers_by_url: _RequestHeadersByUrl,
    ) -> object:
        if policy in (
            LocalLocalResourcePolicy.PASSTHROUGH,
            RemoteLocalResourcePolicy.MEMORY,
        ):
            return value
        if policy is RemoteLocalResourcePolicy.ERROR:
            raise ResourceAccessDeniedError(
                "Local resources are disabled by the resource strategy.",
                reference=value,
                operation="materialize",
            )
        if policy is LocalLocalResourcePolicy.FILE:
            if not isinstance(value, (str, Path)):
                raise InvalidRenderInputError(
                    "The file policy only accepts path values.",
                    operation="materialize",
                    field="resource",
                )
            return self.authorize_local(_candidate(value, template_base)).as_uri()
        if policy in (
            LocalLocalResourcePolicy.FILEHOST,
            RemoteLocalResourcePolicy.FILEHOST,
        ):
            if self._publisher is None:
                raise ResourcePublishError(
                    "The filehost policy requires an asset publisher.",
                    reference=value,
                    operation="publish",
                )
            publish_content: ResourceContent | InlineResource
            if isinstance(value, str):
                value = _candidate(value, template_base)
            if isinstance(value, Path):
                reference = FileResourceRef(self.authorize_local(value))
                publish_content = await self.fetch(reference)
            elif isinstance(value, BytesIO):
                publish_content = InlineResource(value.getvalue())
            elif isinstance(value, bytearray):
                publish_content = InlineResource(bytes(value))
            elif isinstance(value, bytes):
                publish_content = InlineResource(value)
            else:
                raise InvalidRenderInputError(
                    "The filehost policy only accepts paths or bytes.",
                    operation="publish",
                    field="resource",
                )
            published = await self._publisher.publish(
                publish_content,
                lease_id=lease_id,
            )
            _record_published_resource(published, request_headers_by_url)
            return published.url
        raise ResourcePublishError(
            f"Unsupported resource policy: {policy!r}",
            reference=value,
            operation="materialize",
        )

    async def _materialize_scalar(
        self,
        value: object,
        *,
        template_base: Path | None,
        strict: bool | None,
        materializer: _MaterializerSpec,
        lease_id: PublicationLeaseId | None,
        request_headers_by_url: _RequestHeadersByUrl,
    ) -> object:
        policy = self._policy(materializer)
        effective_strict = (
            self._strategy.materialization_policy
            is ResourceMaterializationPolicy.STRICT
            if strict is None
            else strict
        )
        try:
            async with self._scalar_slots:
                if isinstance(
                    policy, (LocalLocalResourcePolicy, RemoteLocalResourcePolicy)
                ):
                    return await self._materialize_with_policy(
                        policy,
                        value,
                        template_base=template_base,
                        lease_id=lease_id,
                        request_headers_by_url=request_headers_by_url,
                    )
                return await self._materialize_with_custom(
                    policy,
                    value,
                    template_base=template_base,
                )
        except Exception as error:
            if isinstance(error, _ConflictingRequestAuthorization):
                raise
            if policy is RemoteLocalResourcePolicy.ERROR or effective_strict:
                if isinstance(error, (ResourceError, InvalidRenderInputError)):
                    raise
                if isinstance(error, FileNotFoundError):
                    raise ResourceNotFoundError(
                        "Resource was not found.",
                        reference=value,
                        operation="materialize",
                        source=error,
                    ) from error
                if isinstance(error, PermissionError):
                    raise ResourceAccessDeniedError(
                        "Resource access was denied.",
                        reference=value,
                        operation="materialize",
                        source=error,
                    ) from error
                raise ResourceFetchError(
                    "Resource materialization failed.",
                    reference=value,
                    operation="materialize",
                    source=error,
                ) from error
            logger.warning(
                "Failed to materialize a resource (non-strict policy): %s",
                type(error).__name__,
            )
            return value

    async def _materialize_any(
        self,
        value: object,
        *,
        template_base: Path | None,
        strict: bool | None,
        materializer: _MaterializerSpec,
        lease_id: PublicationLeaseId | None,
        request_headers_by_url: _RequestHeadersByUrl,
    ) -> object:
        plan = VariableMaterializationPlan.build(
            value,
            budget=self._traversal_budget,
        )
        jobs = tuple(leaf for leaf in plan.leaves if _is_scalar(leaf.value))
        if not jobs:
            return plan.rebuild({})

        resolved: dict[int, object] = {}
        errors: dict[int, Exception] = {}
        failed = anyio.Event()
        cursor = 0
        cursor_lock = anyio.Lock()

        async def take_job() -> tuple[int, object] | None:
            nonlocal cursor
            async with cursor_lock:
                if failed.is_set() or cursor >= len(jobs):
                    return None
                leaf = jobs[cursor]
                cursor += 1
                return leaf.node_index, leaf.value

        async def worker() -> None:
            while (job := await take_job()) is not None:
                node_index, leaf_value = job
                try:
                    resolved[node_index] = await self._materialize_scalar(
                        leaf_value,
                        template_base=template_base,
                        strict=strict,
                        materializer=materializer,
                        lease_id=lease_id,
                        request_headers_by_url=request_headers_by_url,
                    )
                except Exception as error:
                    errors[node_index] = error
                    failed.set()

        worker_count = min(self._traversal_budget.max_concurrency, len(jobs))
        async with anyio.create_task_group() as group:
            for _ in range(worker_count):
                group.start_soon(worker)

        if errors:
            for leaf in jobs:
                if error := errors.get(leaf.node_index):
                    raise error
            raise RuntimeError(
                "Variable materialization failed without a recorded error."
            )

        return plan.rebuild(resolved)

    async def _materialize_template_vars(
        self,
        template_vars: Mapping[str, Any],
        *,
        template_base: str | Path | None = None,
        strict: bool | None = None,
        materializer: _MaterializerSpec = None,
        lease_id: PublicationLeaseId | None = None,
    ) -> _MaterializationResult[dict[str, Any]]:
        request_headers_by_url: _RequestHeadersByUrl = {}
        if not self._should_materialize(materializer):
            return _MaterializationResult(dict(template_vars))
        result = await self._materialize_any(
            template_vars,
            template_base=_normalize_template_base(template_base),
            strict=strict,
            materializer=materializer,
            lease_id=lease_id,
            request_headers_by_url=request_headers_by_url,
        )
        if not isinstance(result, dict):
            raise ResourceFetchError(
                "Materialized template variables must remain a mapping.",
                reference=template_vars,
                operation="materialize",
            )
        if not _is_string_keyed_dict(result):
            raise ResourceFetchError(
                "Materialized template variable keys must remain strings.",
                reference=template_vars,
                operation="materialize",
            )
        return _MaterializationResult(
            result,
            request_headers_by_url,
        )

    async def materialize_template_variables(
        self,
        variables: Mapping[str, object],
        *,
        materializer: ResourceMaterializer,
        strict: bool,
        template_base: Path | None,
    ) -> dict[str, object]:
        """Materialize template data through the internal preparation port."""

        result = await self._materialize_template_vars(
            variables,
            template_base=template_base,
            strict=strict,
            materializer=materializer,
        )
        return result.value

    async def _materialize_resource_url(
        self,
        value: str | Path | bytes,
        *,
        template_base: str | Path | None = None,
        strict: bool | None = None,
        materializer: _MaterializerSpec = None,
        lease_id: PublicationLeaseId | None = None,
    ) -> _MaterializationResult[str]:
        request_headers_by_url: _RequestHeadersByUrl = {}
        result = await self._materialize_any(
            value,
            template_base=_normalize_template_base(template_base),
            strict=strict,
            materializer=materializer,
            lease_id=lease_id,
            request_headers_by_url=request_headers_by_url,
        )
        if not isinstance(result, str):
            raise ResourceFetchError(
                f"Materialized resource is not URL text: {type(result).__name__}.",
                reference=value,
                operation="materialize",
            )
        return _MaterializationResult(result, request_headers_by_url)

    async def _materialize_url_tokens(
        self,
        values: Sequence[str],
        *,
        template_base: str | Path | None = None,
        strict: bool | None = None,
        materializer: _MaterializerSpec = None,
        lease_id: PublicationLeaseId | None = None,
    ) -> _MaterializationResult[list[str]]:
        base = _normalize_template_base(template_base)
        resolved: list[str] = []
        request_headers_by_url: _RequestHeadersByUrl = {}
        for raw in values:
            parsed = _split_resource_url(raw)
            if parsed.scheme or parsed.netloc or raw.startswith(("data:", "#")):
                resolved.append(raw)
                continue
            token_headers_by_url: _RequestHeadersByUrl = {}
            value = await self._materialize_scalar(
                parsed.path,
                template_base=base,
                strict=strict,
                materializer=materializer,
                lease_id=lease_id,
                request_headers_by_url=token_headers_by_url,
            )
            if not isinstance(value, str):
                resolved.append(raw)
                continue
            target = _split_resource_url(value)
            resolved_url = urlunsplit(
                (
                    target.scheme,
                    target.netloc,
                    target.path,
                    parsed.query or target.query,
                    parsed.fragment,
                )
            )
            resolved.append(resolved_url)
            headers = token_headers_by_url.get(value)
            if headers is not None:
                _record_published_resource(
                    PublishedResource(resolved_url, headers),
                    request_headers_by_url,
                )
        return _MaterializationResult(resolved, request_headers_by_url)

    async def clear(self) -> None:
        await self._fetcher.clear()


__all__ = ["ResourceService"]
