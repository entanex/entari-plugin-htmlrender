from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from entari_plugin_htmlrender._graphics_composition import build_graphics_renderer
from entari_plugin_htmlrender.adapters.resources import AnyioWorkerExecutor
from entari_plugin_htmlrender.config import GraphicsSettings
from entari_plugin_htmlrender.errors import (
    CapabilityUnavailableError,
    GraphicsBackendUnavailableError,
    RuntimeUnavailableError,
)
from entari_plugin_htmlrender.graphics import (
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


def _renderer(
    backend: GraphicsBackendName | None,
    *,
    admission: OperationAdmissionGate | None = None,
):
    return build_graphics_renderer(
        GraphicsSettings(backend=backend, max_pixels=64, max_concurrency=1),
        worker=AnyioWorkerExecutor(),
        observer=NoopOperationObserver(),
        operation_admission=admission or OperationAdmissionGate(),
    )


@pytest.mark.parametrize("backend", ["pillow", "skia"])
async def test_selected_backend_is_hidden_behind_graphics_renderer(
    backend: GraphicsBackendName,
) -> None:
    image = await _renderer(backend).rasterize(_scene())

    assert (image.format, image.width, image.height) == ("png", 4, 3)


async def test_unconfigured_graphics_retains_stable_renderer_shape() -> None:
    renderer = _renderer(None)

    with pytest.raises(CapabilityUnavailableError) as raised:
        await renderer.rasterize(_scene())

    assert raised.value.capability == "graphics"


async def test_selected_missing_backend_reports_graphics_backend(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        "entari_plugin_htmlrender._graphics_composition.find_spec",
        return_value=None,
    )
    renderer = _renderer("pillow")

    with pytest.raises(GraphicsBackendUnavailableError) as raised:
        await renderer.rasterize(_scene())

    assert raised.value.backend == "pillow"
    assert "entari-plugin-htmlrender[pillow]" in raised.value.reason


async def test_graphics_renderer_shares_runtime_admission() -> None:
    admission = OperationAdmissionGate()
    renderer = _renderer("pillow", admission=admission)
    await admission.stop_accepting_and_drain()

    with pytest.raises(RuntimeUnavailableError):
        await renderer.rasterize(_scene())
