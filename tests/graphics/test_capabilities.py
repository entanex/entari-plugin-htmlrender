from __future__ import annotations

from typing import get_type_hints

from entari_plugin_htmlrender.graphics import (
    GraphicsRenderer,
    RasterEncodeOptions,
    RasterScene,
)
from entari_plugin_htmlrender.rendering import RenderedImage


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


def test_public_renderer_annotations_are_runtime_resolvable() -> None:
    annotations = get_type_hints(GraphicsRenderer.rasterize)

    assert annotations == {
        "scene": RasterScene,
        "output": RasterEncodeOptions,
        "return": RenderedImage,
    }
