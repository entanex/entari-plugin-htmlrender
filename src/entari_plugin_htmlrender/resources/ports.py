from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Any, ParamSpec, Protocol, TypeVar

from .config import ResourceStrategy
from .models import (
    InlineResource,
    NotModified,
    PublicationLeaseId,
    PublishedResource,
    ResourceContent,
    ResourceRef,
    ResourceRevision,
)
from .templating import ExtensionSpec, FilterCallable, TemplateSource

R = TypeVar("R")
P = ParamSpec("P")


class ResourceFetcher(Protocol):
    """Fetch content for explicit resource locators.

    This source-side port does not accept :class:`InlineResource`, because an
    inline payload has no source to fetch or revalidate.
    """

    async def fetch(
        self,
        reference: ResourceRef,
        *,
        refresh: bool = False,
    ) -> ResourceContent: ...

    async def fetch_if_changed(
        self,
        reference: ResourceRef,
        revision: ResourceRevision,
    ) -> ResourceContent | NotModified:
        """Fetch only when the source moved past ``revision``.

        The caller supplies the revision it already holds; the reader maps
        it to a source-native conditional read (``If-None-Match`` /
        ``If-Modified-Since`` for HTTP, a stat compare for files) and
        returns :class:`NotModified` when the cached bytes are still
        current. Fetchers keep no validator state of their own.
        """
        ...

    async def fetch_revision(
        self, reference: ResourceRef
    ) -> ResourceRevision | None: ...

    async def invalidate(self, reference: ResourceRef) -> None: ...

    async def clear(self) -> None: ...


class ProviderResourceAccess(Protocol):
    """Policy-bound resource operations available to engine providers."""

    @property
    def strategy(self) -> ResourceStrategy: ...

    def authorize_local(self, path: Path) -> Path: ...

    async def fetch_bytes(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> bytes: ...


class LocalAccessPolicy(Protocol):
    def authorize(self, path: Path) -> Path: ...


class RemoteAccessPolicy(Protocol):
    """Egress policy consulted before and during every remote fetch.

    ``authorize_address`` must be called with each resolved address and with
    every redirect hop so DNS answers cannot smuggle the request into a
    blocked network after the initial URL check passed.
    """

    @property
    def max_redirects(self) -> int: ...

    def authorize_url(self, url: str) -> None: ...

    def authorize_address(
        self,
        url: str,
        address: IPv4Address | IPv6Address,
    ) -> None: ...


class AssetPublisher(Protocol):
    """Internal multi-asset publication backend.

    Provider integrations may group many assets under one lease.  Callers do
    not receive this ownership API; :class:`ResourceAccess.publish` exposes a
    scoped publication instead.
    """

    def create_lease(self) -> PublicationLeaseId: ...

    async def release(self, lease_id: PublicationLeaseId) -> None: ...

    async def publish(
        self,
        content: ResourceContent | InlineResource,
        *,
        lease_id: PublicationLeaseId | None = None,
        suffix: str | None = None,
    ) -> PublishedResource: ...

    async def startup(self) -> None: ...

    async def clear(self) -> None: ...

    async def aclose(self) -> None: ...


class WorkerExecutor(Protocol):
    async def run_sync(
        self,
        function: Callable[P, R],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R: ...


class TemplateCompiler(Protocol):
    async def render(
        self,
        template_path: TemplateSource,
        template_name: str,
        variables: Mapping[str, Any],
        *,
        filters: Mapping[str, FilterCallable] | None = None,
        immutable: bool = False,
        extensions: Sequence[ExtensionSpec] = (),
    ) -> str: ...

    async def clear(self) -> None: ...


class ResourceMaterializer(Protocol):
    """Asynchronously materialize one document-local value."""

    async def materialize(
        self,
        value: object,
        *,
        template_base: Path | None = None,
    ) -> object: ...


class ResourceAccess(Protocol):
    """Minimal caller contract for fetching and scoped publication."""

    async def fetch(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> ResourceContent: ...

    async def fetch_bytes(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> bytes: ...

    async def fetch_text(
        self,
        resource: ResourceRef,
        *,
        encoding: str = "utf-8",
        errors: str = "strict",
        refresh: bool = False,
    ) -> str: ...

    def publish(
        self,
        content: ResourceContent | InlineResource,
        *,
        suffix: str | None = None,
    ) -> AbstractAsyncContextManager[PublishedResource]: ...


class PreparationResourceAccess(
    ResourceAccess,
    ProviderResourceAccess,
    Protocol,
):
    """Internal preparation contract; never exposed as runtime caller API."""

    async def materialize_template_variables(
        self,
        variables: Mapping[str, object],
        *,
        materializer: ResourceMaterializer,
        strict: bool,
        template_base: Path | None,
    ) -> dict[str, object]: ...


__all__ = [
    "AssetPublisher",
    "LocalAccessPolicy",
    "PreparationResourceAccess",
    "ProviderResourceAccess",
    "RemoteAccessPolicy",
    "ResourceAccess",
    "ResourceFetcher",
    "ResourceMaterializer",
    "TemplateCompiler",
    "WorkerExecutor",
]
