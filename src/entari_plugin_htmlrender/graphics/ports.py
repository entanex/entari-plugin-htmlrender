"""Stable graphics contract implemented by the selected adapter."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Public protocol annotations must remain resolvable through get_type_hints().
from entari_plugin_htmlrender.rendering.artifacts import RenderedImage  # noqa: TC001

from .models import (
    DEFAULT_RASTER_ENCODE_OPTIONS,
    RasterEncodeOptions,
    RasterScene,
)


@runtime_checkable
class GraphicsRenderer(Protocol):
    """Rasterize neutral physical-pixel scenes without exposing backend selection."""

    async def rasterize(
        self,
        scene: RasterScene,
        *,
        output: RasterEncodeOptions = DEFAULT_RASTER_ENCODE_OPTIONS,
    ) -> RenderedImage: ...


__all__ = ["GraphicsRenderer"]
