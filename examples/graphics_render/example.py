"""Render one backend-neutral scene with Pillow or Skia."""

from __future__ import annotations

from typing import Literal

from entari_plugin_htmlrender import RenderedImage, RuntimeSource, resolve_runtime
from entari_plugin_htmlrender.graphics import (
    FillRect,
    PixelRect,
    RasterScene,
    RenderRasterSceneRequest,
    RGBAColor,
)


async def render_scene(
    runtime: RuntimeSource,
    backend: Literal["pillow", "skia"] = "pillow",
) -> RenderedImage:
    extensions = resolve_runtime(runtime).extensions
    renderer = extensions.pillow if backend == "pillow" else extensions.skia
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
    return await renderer.render(RenderRasterSceneRequest(scene))
