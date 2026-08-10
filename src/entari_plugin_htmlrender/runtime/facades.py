"""Lifecycle-bound implementation of the caller resource contract."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.resources.models import (
        InlineResource,
        PublishedResource,
        ResourceContent,
        ResourceRef,
    )
    from entari_plugin_htmlrender.resources.ports import ResourceAccess


@final
class _AdmittedResourceAccess:
    """Keep retained resource operations inside the runtime drain boundary."""

    def __init__(
        self,
        delegate: ResourceAccess,
        admission: OperationAdmissionGate,
    ) -> None:
        self._delegate = delegate
        self._admission = admission

    async def fetch(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> ResourceContent:
        async with self._admission.operation("resource.fetch"):
            return await self._delegate.fetch(resource, refresh=refresh)

    async def fetch_bytes(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> bytes:
        async with self._admission.operation("resource.fetch_bytes"):
            return await self._delegate.fetch_bytes(resource, refresh=refresh)

    async def fetch_text(
        self,
        resource: ResourceRef,
        *,
        encoding: str = "utf-8",
        errors: str = "strict",
        refresh: bool = False,
    ) -> str:
        async with self._admission.operation("resource.fetch_text"):
            return await self._delegate.fetch_text(
                resource,
                encoding=encoding,
                errors=errors,
                refresh=refresh,
            )

    @asynccontextmanager
    async def publish(
        self,
        content: ResourceContent | InlineResource,
        *,
        suffix: str | None = None,
    ) -> AsyncIterator[PublishedResource]:
        async with (
            self._admission.operation("resource.publish"),
            self._delegate.publish(content, suffix=suffix) as published,
        ):
            yield published


__all__: list[str] = []
