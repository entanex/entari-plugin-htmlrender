from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from entari_plugin_htmlrender._graphics_composition import build_graphics_composition
from entari_plugin_htmlrender.adapters.resources import AnyioWorkerExecutor
from entari_plugin_htmlrender.config import GraphicsSettings
from entari_plugin_htmlrender.errors import (
    CapabilityUnavailableError,
    GraphicsBackendUnavailableError,
    RuntimeUnavailableError,
)
from entari_plugin_htmlrender.graphics import (
    PILLOW_RASTER_SCENE_RENDERER,
    SKIA_RASTER_SCENE_RENDERER,
    FillRect,
    GraphicsBackendName,
    PixelRect,
    RasterScene,
    RGBAColor,
)
from entari_plugin_htmlrender.rendering import (
    NoopOperationObserver,
    OperationAdmissionGate,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _scene() -> RasterScene:
    return RasterScene(
        4,
        3,
        background=RGBAColor(0, 0, 0, 0),
        commands=(FillRect(PixelRect(1, 1, 2, 1), RGBAColor(255, 0, 0)),),
    )


def _composition(
    backend: GraphicsBackendName | None = None,
    *,
    backends: tuple[GraphicsBackendName, ...] = (),
    admission: OperationAdmissionGate | None = None,
):
    return build_graphics_composition(
        GraphicsSettings(
            backend=backend,
            backends=backends,
            max_pixels=64,
            max_concurrency=1,
        ),
        worker=AnyioWorkerExecutor(),
        observer=NoopOperationObserver(),
        operation_admission=admission or OperationAdmissionGate(),
    )


@pytest.mark.parametrize("backend", ["pillow", "skia"])
async def test_selected_backend_is_hidden_behind_graphics_renderer(
    backend: GraphicsBackendName,
) -> None:
    image = await _composition(backend).primary.rasterize(_scene())

    assert (image.format, image.width, image.height) == ("png", 4, 3)


async def test_unconfigured_graphics_retains_stable_renderer_shape() -> None:
    composition = _composition()

    with pytest.raises(CapabilityUnavailableError) as raised:
        await composition.primary.rasterize(_scene())

    assert raised.value.capability == "graphics"
    assert composition.capabilities.names() == frozenset()


async def test_selected_missing_backend_reports_graphics_backend(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        "entari_plugin_htmlrender._graphics_composition.find_spec",
        return_value=None,
    )
    composition = _composition("pillow")

    with pytest.raises(GraphicsBackendUnavailableError) as raised:
        await composition.primary.rasterize(_scene())

    assert raised.value.backend == "pillow"
    assert "entari-plugin-htmlrender[pillow]" in raised.value.reason


async def test_graphics_renderer_shares_runtime_admission() -> None:
    admission = OperationAdmissionGate()
    composition = _composition(
        admission=admission,
        backends=("pillow", "skia"),
    )
    pillow = composition.capabilities.require(PILLOW_RASTER_SCENE_RENDERER)
    skia = composition.capabilities.require(SKIA_RASTER_SCENE_RENDERER)
    await admission.stop_accepting_and_drain()

    for renderer in (composition.primary, pillow, skia):
        with pytest.raises(RuntimeUnavailableError):
            await renderer.rasterize(_scene())


async def test_backends_compose_independently_with_separate_budgets() -> None:
    composition = _composition(backends=("pillow", "skia"))
    pillow = composition.capabilities.require(PILLOW_RASTER_SCENE_RENDERER)
    skia = composition.capabilities.require(SKIA_RASTER_SCENE_RENDERER)
    pillow_state = vars(pillow)
    skia_state = vars(skia)

    assert composition.primary is pillow
    assert pillow is not skia
    assert pillow_state["_worker"] is skia_state["_worker"]
    assert pillow_state["_observer"] is skia_state["_observer"]
    assert pillow_state["_operation_admission"] is skia_state["_operation_admission"]
    assert pillow_state["_budget"] is not skia_state["_budget"]

    pillow_image, skia_image = (
        await pillow.rasterize(_scene()),
        await skia.rasterize(_scene()),
    )
    assert (pillow_image.format, pillow_image.width, pillow_image.height) == (
        "png",
        4,
        3,
    )
    assert (skia_image.format, skia_image.width, skia_image.height) == (
        "png",
        4,
        3,
    )


def test_legacy_backend_selects_the_primary_of_a_configured_list() -> None:
    composition = _composition("skia", backends=("pillow", "skia"))

    assert composition.primary is composition.capabilities.require(
        SKIA_RASTER_SCENE_RENDERER
    )


def test_missing_secondary_backend_is_absent_from_capabilities(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        "entari_plugin_htmlrender._graphics_composition.find_spec",
        side_effect=lambda module: None if module == "skia" else object(),
    )
    composition = _composition(backends=("pillow", "skia"))

    assert composition.capabilities.get(PILLOW_RASTER_SCENE_RENDERER) is not None
    with pytest.raises(CapabilityUnavailableError) as raised:
        composition.capabilities.require(SKIA_RASTER_SCENE_RENDERER)
    assert raised.value.capability == "graphics.skia.raster_scene_renderer"
