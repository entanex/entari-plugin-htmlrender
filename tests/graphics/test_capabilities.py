from __future__ import annotations

from typing import get_type_hints

from entari_plugin_htmlrender.graphics import (
    PILLOW_RASTER_SCENE_RENDERER,
    SKIA_RASTER_SCENE_RENDERER,
    GraphicsRenderer,
    RasterEncodeOptions,
    RasterScene,
)
from entari_plugin_htmlrender.rendering import CapabilityCatalog, RenderedImage


class _Renderer:
    async def rasterize(
        self,
        scene: RasterScene,
        *,
        output: RasterEncodeOptions = RasterEncodeOptions(),  # noqa: B008
    ) -> RenderedImage:
        del scene, output
        raise NotImplementedError


def test_graphics_renderer_is_a_backend_neutral_contract() -> None:
    renderer = _Renderer()
    assert isinstance(renderer, GraphicsRenderer)


def test_pillow_and_skia_have_distinct_typed_capability_keys() -> None:
    pillow = _Renderer()
    skia = _Renderer()
    catalog = (
        CapabilityCatalog()
        .with_capability(PILLOW_RASTER_SCENE_RENDERER, pillow)
        .with_capability(SKIA_RASTER_SCENE_RENDERER, skia)
    )

    assert catalog.require(PILLOW_RASTER_SCENE_RENDERER) is pillow
    assert catalog.require(SKIA_RASTER_SCENE_RENDERER) is skia
    assert PILLOW_RASTER_SCENE_RENDERER.name == "graphics.pillow.raster_scene_renderer"
    assert SKIA_RASTER_SCENE_RENDERER.name == "graphics.skia.raster_scene_renderer"


def test_public_renderer_annotations_are_runtime_resolvable() -> None:
    annotations = get_type_hints(GraphicsRenderer.rasterize)

    assert annotations == {
        "scene": RasterScene,
        "output": RasterEncodeOptions,
        "return": RenderedImage,
    }
