from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from entari_plugin_htmlrender.graphics import (
    FillRect,
    GraphicsBackendName,
    PixelRect,
    RasterBackendUnavailable,
    RasterScene,
    RenderRasterSceneRequest,
    RGBAColor,
)
from entari_plugin_htmlrender.host.composition import compose_runtime
from entari_plugin_htmlrender.host.config import RenderSettings
from entari_plugin_htmlrender.rendering import ProviderLifecycleError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _settings(*backends: GraphicsBackendName) -> RenderSettings:
    return RenderSettings.model_validate(
        {
            "graphics": {
                "backends": backends,
                "max_pixels": 64,
                "max_concurrency": 1,
            }
        }
    )


def _request() -> RenderRasterSceneRequest:
    return RenderRasterSceneRequest(
        RasterScene(
            4,
            3,
            background=RGBAColor(0, 0, 0, 0),
            commands=(FillRect(PixelRect(1, 1, 2, 1), RGBAColor(255, 0, 0)),),
        )
    )


async def test_both_graphics_backends_compose_without_an_html_provider() -> None:
    application = compose_runtime(_settings("pillow", "skia")).build_runtime()
    pillow = application.extensions.pillow
    skia = application.extensions.skia

    try:
        pillow_image = await pillow.render(_request())
        skia_image = await skia.render(_request())
    finally:
        await application.aclose()

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
    assert application.renderer.supported_commands == frozenset(
        {"render_template_html"}
    )


async def test_retained_graphics_capabilities_share_application_admission() -> None:
    application = compose_runtime(_settings("pillow", "skia")).build_runtime()
    pillow = application.extensions.pillow
    skia = application.extensions.skia

    await application.aclose()

    for renderer in (pillow, skia):
        with pytest.raises(ProviderLifecycleError, match="closing or closed"):
            await renderer.render(_request())


def test_configured_missing_graphics_extra_fails_with_install_hint(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        "entari_plugin_htmlrender.host.graphics.find_spec",
        return_value=None,
    )

    with pytest.raises(
        RasterBackendUnavailable,
        match=r"entari-plugin-htmlrender\[pillow\]",
    ):
        compose_runtime(_settings("pillow")).build_runtime()
