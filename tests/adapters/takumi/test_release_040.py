"""Compatibility checks for the published takumi-py 0.4.0 API."""

from __future__ import annotations

from base64 import b64decode, b64encode
from importlib.metadata import version
from pathlib import Path
import re
from typing import TYPE_CHECKING, Callable

import pytest

from entari_plugin_htmlrender.adapters.takumi import TakumiConfig
from entari_plugin_htmlrender.adapters.takumi.advanced import TakumiAPIAdapter
from entari_plugin_htmlrender.adapters.takumi.runtime import create_runtime_state
from entari_plugin_htmlrender.errors import ProviderExecutionError
from tests.adapters.takumi.helpers import resource_service

if TYPE_CHECKING:
    from entari_plugin_htmlrender.adapters.takumi.types import AnimationImageFormat

takumi_py = pytest.importorskip("takumi_py")

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_KATEX_FONT_CSS = (
    _PROJECT_ROOT
    / "src"
    / "entari_plugin_htmlrender"
    / "templates"
    / "markdown"
    / "katex"
    / "katex.min.b64_fonts.css"
)
_FONT_DATA_RE = re.compile(r"data:font/woff2;base64,([^\")]+)")


@pytest.fixture(scope="module")
def installed_takumi_version() -> str:
    return version("takumi-py")


@pytest.fixture(scope="module")
def release_api() -> None:
    assert hasattr(takumi_py, "UnicodeRange")
    assert {
        "cache_font",
        "cached_fonts",
        "unregister_font",
        "clear_fonts",
    } <= set(dir(takumi_py.Renderer))


async def test_release_exposes_only_published_document_free_api(
    installed_takumi_version: str,
    release_api: None,
) -> None:
    del release_api
    assert installed_takumi_version == "0.4.0"
    assert not hasattr(takumi_py, "Document")
    assert not hasattr(takumi_py, "CompiledDocument")
    assert not hasattr(takumi_py, "math")


async def test_release_renders_static_png_and_svg() -> None:
    state = await create_runtime_state(
        TakumiConfig(),
        resources=resource_service(),
    )
    api = TakumiAPIAdapter(state)
    try:
        png = await api.render_html(
            '<div style="width: 12px; height: 7px; background: #123456"></div>',
            width=12,
            height=7,
        )
        svg = await api.render_svg_html(
            '<div style="width: 12px; height: 7px; background: #123456"></div>',
            width=12,
            height=7,
        )
    finally:
        await state.aclose()

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert svg.startswith("<svg ")


async def test_release_caches_inline_data_images() -> None:
    state = await create_runtime_state(
        TakumiConfig(cache_max_bytes=8 * 1024 * 1024),
        resources=resource_service(),
    )
    api = TakumiAPIAdapter(state)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"></svg>'
    data_uri = f"data:image/svg+xml;base64,{b64encode(svg).decode('ascii')}"
    try:
        rendered = await api.render_html(
            f'<img src="{data_uri}" style="width: 2px; height: 2px">',
            width=2,
            height=2,
        )
    finally:
        await state.aclose()

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(
    ("image_format", "max_fps", "signature"),
    [
        ("webp", 90, lambda data: data.startswith(b"RIFF") and data[8:12] == b"WEBP"),
        ("apng", 90, lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
        ("gif", 50, lambda data: data.startswith(b"GIF89a")),
    ],
)
async def test_release_enforces_animation_fps_limits(
    image_format: AnimationImageFormat,
    max_fps: int,
    signature: Callable[[bytes], bool],
) -> None:
    state = await create_runtime_state(
        TakumiConfig(),
        resources=resource_service(),
    )
    api = TakumiAPIAdapter(state)
    scenes = (
        takumi_py.AnimationScene(
            {
                "type": "container",
                "style": {
                    "width": "2px",
                    "height": "2px",
                    "backgroundColor": "black",
                },
            },
            duration_ms=30,
        ),
    )
    try:
        encoded = await api.render_animation(
            scenes,
            width=2,
            height=2,
            format=image_format,
            fps=max_fps,
        )
        with pytest.raises(ProviderExecutionError) as raised:
            await api.render_animation(
                scenes,
                width=2,
                height=2,
                format=image_format,
                fps=max_fps + 1,
            )
    finally:
        await state.aclose()

    assert signature(encoded)
    cause = raised.value.__cause__
    assert isinstance(cause, ValueError)
    assert f"fps must not exceed {max_fps}" in str(cause)


async def test_release_font_api_unicode_cache_and_release(
    release_api: None,
) -> None:
    del release_api
    match = _FONT_DATA_RE.search(_KATEX_FONT_CSS.read_text(encoding="utf-8"))
    assert match is not None

    source = takumi_py.FontResource(
        data=b64decode(match.group(1)),
        name="Release Font",
        unicode_range=[(0x0000, 0x007F)],
    )
    state = await create_runtime_state(
        TakumiConfig(load_default_fonts=False),
        resources=resource_service(),
    )
    api = TakumiAPIAdapter(state)
    try:
        assert await api.register_font(source) == ("Release Font",)
        assert api.registered_font_families == ("Release Font",)
        assert await api.unregister_font("Release Font") is True
        assert await api.unregister_font("Release Font") is False
        assert await api.cache_font(source, "memory:release-font") == ("Release Font",)
        assert await api.cached_fonts("memory:release-font") == ("Release Font",)
        await api.clear_fonts()
        assert await api.cached_fonts("memory:release-font") is None
        assert api.registered_font_families == ()
    finally:
        await state.aclose()
