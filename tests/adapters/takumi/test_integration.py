from __future__ import annotations

from base64 import b64decode
from pathlib import Path
import re
import struct

import pytest

from entari_plugin_htmlrender.adapters.takumi import TakumiConfig, TakumiRuntimeError
from entari_plugin_htmlrender.adapters.takumi.advanced import TakumiAPIAdapter
from entari_plugin_htmlrender.adapters.takumi.api import TakumiSessionAdapter
from entari_plugin_htmlrender.adapters.takumi.runtime import create_runtime_state
from tests.adapters.takumi.helpers import resource_service
from tests.image_fixtures import encoded_image

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


async def test_takumi_native_boundary_renders_extension_output() -> None:
    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    try:
        rendered = await TakumiSessionAdapter(state).render_html(
            '<div style="width:32px;height:16px;background:#00f"></div>',
            width=32,
            height=16,
            device_pixel_ratio=2,
        )
    finally:
        await state.aclose()

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", rendered[16:24]) == (64, 32)


async def test_takumi_native_error_is_translated_at_runtime_boundary() -> None:
    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    try:
        with pytest.raises(TakumiRuntimeError, match="compile") as raised:
            await state.compile_stylesheet("}", lossy=False)
    finally:
        await state.aclose()

    assert isinstance(raised.value.__cause__, takumi_py.StyleSheetError)


async def test_takumi_native_renders_managed_compiled_document() -> None:
    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    api = TakumiAPIAdapter(state)
    image = ("memory:avatar", encoded_image("png", width=2, height=2))
    html = '<div class="card"><img src="memory:avatar">Hello</div>'
    stylesheet = (
        ".card { width: 40px; height: 24px; background: #fff; "
        "font-size: 10px; } img { width: 2px; height: 2px; }"
    )
    try:
        document = await api.compile_html(
            html,
            stylesheets=(stylesheet,),
            images=(image,),
        )
        assert document.images

        rendered = await api.render_compiled(document, width=40, height=24)
        measured = await api.measure_compiled(document, width=40, height=24)
        svg = await api.render_svg_compiled(document, width=40, height=24)
        assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
        assert measured.width == 40
        assert measured.height == 24
        assert svg.startswith("<svg ")

    finally:
        await state.aclose()


async def test_takumi_native_font_lifecycle_updates_managed_records(
    tmp_path: Path,
) -> None:
    match = _FONT_DATA_RE.search(_KATEX_FONT_CSS.read_text(encoding="utf-8"))
    assert match is not None
    font_path = tmp_path / "fixture.woff2"
    font_path.write_bytes(b64decode(match.group(1)))

    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    api = TakumiAPIAdapter(state)
    try:
        families = await api.register_font_file(
            font_path,
            name="Htmlrender Smoke",
            unicode_range=((0x0000, 0x007F),),
        )
        assert families == ("Htmlrender Smoke",)
        assert api.registered_font_families == families
        assert await api.unregister_font("Htmlrender Smoke") is True
        assert api.registered_font_families == ()

        source = takumi_py.FontResource(
            data=font_path.read_bytes(),
            name="Htmlrender Smoke",
            unicode_range=[(0x0000, 0x007F)],
        )
        assert await api.cache_font(source, "memory:smoke-font") == families
        assert await api.cached_fonts("memory:smoke-font") == families
        await api.clear_fonts()
        assert await api.cached_fonts("memory:smoke-font") is None
        assert api.registered_font_families == ()
    finally:
        await state.aclose()
