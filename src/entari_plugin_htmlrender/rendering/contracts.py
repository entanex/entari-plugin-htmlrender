"""Framework-neutral contracts for the ordinary rendering call path."""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003
from typing import Protocol, runtime_checkable

from entari_plugin_htmlrender.preparation.models import (
    PreparedHtml,
    RasterOptions,
    TemplateRef,
)
from entari_plugin_htmlrender.resources.config import (  # noqa: TC001
    ResourceMaterializationPolicy,
)
from entari_plugin_htmlrender.resources.models import ResourceRef  # noqa: TC001

from .artifacts import RenderedHtml, RenderedImage  # noqa: TC001
from .models import RenderOperation  # noqa: TC001

_DEFAULT_RASTER_OPTIONS = RasterOptions()


@runtime_checkable
class HtmlRenderer(Protocol):
    """Rasterize caller content without exposing provider implementation types."""

    @property
    def supported_operations(self) -> frozenset[RenderOperation]: ...

    def supports(self, operation: RenderOperation) -> bool: ...

    async def rasterize_html(
        self,
        html: str,
        *,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        base_url: str | None = None,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage: ...

    async def rasterize_text(
        self,
        text: str,
        *,
        stylesheet: ResourceRef | None = None,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage: ...

    async def rasterize_markdown(
        self,
        source: str | ResourceRef,
        *,
        stylesheet: ResourceRef | None = None,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage: ...

    async def rasterize_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object] | None = None,
        *,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage: ...

    async def rasterize_prepared(
        self,
        prepared: PreparedHtml,
        *,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage: ...


@runtime_checkable
class TemplateRenderer(Protocol):
    """Render one logical template into an HTML artifact."""

    async def render(
        self,
        template: TemplateRef,
        variables: Mapping[str, object] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> RenderedHtml: ...


__all__ = ["HtmlRenderer", "TemplateRenderer"]
