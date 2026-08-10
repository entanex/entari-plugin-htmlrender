from __future__ import annotations

from entari_plugin_htmlrender.graphics import (
    PILLOW_RASTER_SCENE_RENDERER,
    SKIA_RASTER_SCENE_RENDERER,
)
from entari_plugin_htmlrender.providers.sdk import (
    PLAYWRIGHT_PROVIDER_ID,
    RESERVED_PROVIDER_IDS,
    TAKUMI_PROVIDER_ID,
)


def test_graphics_backends_are_not_html_engine_identifiers() -> None:
    html_backends = {
        PLAYWRIGHT_PROVIDER_ID,
        TAKUMI_PROVIDER_ID,
    }

    assert html_backends == {"playwright", "takumi"}
    assert html_backends == RESERVED_PROVIDER_IDS
    assert "pillow" not in html_backends
    assert "skia" not in html_backends
    assert "pillow" not in RESERVED_PROVIDER_IDS
    assert "skia" not in RESERVED_PROVIDER_IDS


def test_graphics_capability_names_do_not_share_provider_namespace() -> None:
    assert PILLOW_RASTER_SCENE_RENDERER.name.startswith("graphics.pillow.")
    assert SKIA_RASTER_SCENE_RENDERER.name.startswith("graphics.skia.")
