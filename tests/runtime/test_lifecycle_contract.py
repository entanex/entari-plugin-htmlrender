"""Initial lifecycle contract for the composed runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    RuntimeUnavailableError,
)
from entari_plugin_htmlrender.graphics import RasterEncodeOptions, RasterScene
from entari_plugin_htmlrender.rendering.models import RenderOperation
from entari_plugin_htmlrender.resources import FileResourceRef
from entari_plugin_htmlrender.runtime import RuntimeState

if TYPE_CHECKING:
    from pathlib import Path


async def test_open_state_describes_lazy_and_explicit_startup() -> None:
    runtime = build_runtime_plan(HtmlRenderConfig()).build_runtime()

    assert runtime.state is RuntimeState.OPEN
    await runtime.startup()
    assert runtime.state is RuntimeState.OPEN

    await runtime.aclose()
    assert runtime.state is RuntimeState.CLOSED


async def test_closed_runtime_precedes_feature_selection_for_all_facades(
    tmp_path: Path,
) -> None:
    runtime = build_runtime_plan(HtmlRenderConfig()).build_runtime()
    await runtime.aclose()

    with pytest.raises(RuntimeUnavailableError) as render_error:
        await runtime.renderer.rasterize_html("<p>closed</p>")
    assert render_error.value.state == "closed"
    assert render_error.value.operation == RenderOperation.HTML_TO_IMAGE.value

    with pytest.raises(RuntimeUnavailableError) as resource_error:
        await runtime.resources.fetch(FileResourceRef(tmp_path / "missing"))
    assert resource_error.value.state == "closed"
    assert resource_error.value.operation == "resource.fetch"

    with pytest.raises(RuntimeUnavailableError) as graphics_error:
        await runtime.graphics.rasterize(RasterScene(1, 1))
    assert graphics_error.value.state == "closed"
    assert graphics_error.value.operation == RenderOperation.RASTER_SCENE_TO_IMAGE.value


@pytest.mark.parametrize(
    ("scene", "output", "field"),
    [
        (object(), None, "scene"),
        (RasterScene(1, 1), object(), "output"),
    ],
)
async def test_graphics_rejects_invalid_runtime_types(
    scene: object,
    output: object | None,
    field: str,
) -> None:
    runtime = build_runtime_plan(HtmlRenderConfig()).build_runtime()

    with pytest.raises(InvalidRenderInputError) as raised:
        if output is None:
            await runtime.graphics.rasterize(cast("RasterScene", scene))
        else:
            await runtime.graphics.rasterize(
                cast("RasterScene", scene),
                output=cast("RasterEncodeOptions", output),
            )

    assert raised.value.operation == RenderOperation.RASTER_SCENE_TO_IMAGE.value
    assert raised.value.field == field
