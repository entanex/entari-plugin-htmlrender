"""Rasterize one backend-neutral scene through an injected graphics contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from entari_plugin_htmlrender.graphics import (
    FillRect,
    PixelRect,
    RasterScene,
    RGBAColor,
)

if TYPE_CHECKING:
    from entari_plugin_htmlrender import RenderedImage
    from entari_plugin_htmlrender.graphics import GraphicsRenderer


async def rasterize_scene(
    graphics: GraphicsRenderer,
) -> RenderedImage:
    scene = RasterScene(
        width=640,
        height=360,
        background=RGBAColor(15, 23, 42),
        commands=(
            FillRect(PixelRect(48, 48, 544, 264), RGBAColor(30, 41, 59)),
            FillRect(PixelRect(80, 88, 208, 184), RGBAColor(139, 92, 246)),
            FillRect(PixelRect(320, 88, 240, 48), RGBAColor(56, 189, 248)),
            FillRect(PixelRect(320, 160, 184, 32), RGBAColor(45, 212, 191, 192)),
        ),
    )
    return await graphics.rasterize(scene)
