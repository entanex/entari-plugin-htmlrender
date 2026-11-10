from __future__ import annotations

from pathlib import Path
import struct

import pytest

from entari_plugin_htmlrender.adapters.takumi import TakumiConfig, TakumiRuntimeError
from entari_plugin_htmlrender.adapters.takumi.advanced import TakumiAPIAdapter
from entari_plugin_htmlrender.adapters.takumi.api import TakumiSessionAdapter
from entari_plugin_htmlrender.adapters.takumi.runtime import create_runtime_state
from tests.adapters.takumi.helpers import resource_service
from tests.image_fixtures import encoded_image

takumi_py = pytest.importorskip("takumi_py")

_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/SFNS.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
)


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


async def test_native_methods_are_not_projected_onto_the_managed_session() -> None:
    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    try:
        session = TakumiSessionAdapter(state)
        assert not hasattr(session, "compile_node")
        assert not hasattr(session, "compile_keyframes")
    finally:
        await state.aclose()


async def test_takumi_native_error_is_translated_at_runtime_boundary() -> None:
    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    try:
        with pytest.raises(TakumiRuntimeError, match="compile") as raised:
            await state.compile_stylesheet("}", lossy=False)
    finally:
        await state.aclose()

    assert isinstance(raised.value.__cause__, takumi_py.StyleSheetError)


async def test_takumi_advanced_api_real_native_chain() -> None:
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

        assert (
            await api.render_html(
                html,
                stylesheets=(stylesheet,),
                images=(image,),
                width=40,
                height=24,
            )
        ).startswith(b"\x89PNG\r\n\x1a\n")
        assert (await api.measure_html(html, width=40, height=24)).width == 40
        assert (await api.render_svg_html(html, width=40, height=24)).startswith(
            "<svg "
        )

        node = await api.compile_node(
            {
                "type": "container",
                "children": [{"type": "text", "text": "Node"}],
            },
            validate=True,
        )
        assert isinstance(node, takumi_py.CompiledNode)
        assert isinstance(
            await api.compile_stylesheet("div { color: red }"),
            takumi_py.CompiledStyleSheet,
        )
        assert isinstance(
            await api.compile_keyframes(
                {
                    "fade": {
                        "from": {"opacity": 0},
                        "to": {"opacity": 1},
                    }
                }
            ),
            takumi_py.CompiledStyleSheet,
        )

        node_input: dict[str, object] = {
            "type": "container",
            "children": [{"type": "text", "text": "Node"}],
        }
        assert (
            await api.render_node(node_input, width=40, height=24, validate=True)
        ).startswith(b"\x89PNG\r\n\x1a\n")
        assert (await api.measure_node(node_input, width=40, height=24)).width > 0
        assert (await api.render_svg_node(node_input, width=40, height=24)).startswith(
            "<svg "
        )

        scenes = (
            takumi_py.AnimationScene(node=node_input, duration_ms=60),
            takumi_py.AnimationScene(node=node, duration_ms=60),
        )
        animation = await api.render_animation(
            scenes,
            width=20,
            height=20,
            format="gif",
            fps=10,
        )
        sequence_frame = await api.render_sequence_at_time(
            scenes,
            30,
            width=20,
            height=20,
        )
        assert animation.startswith(b"GIF89a")
        assert sequence_frame.startswith(b"\x89PNG\r\n\x1a\n")

        raw_frames = (
            takumi_py.RawAnimationFrame(
                data=b"\xff\x00\x00\xff" * 4,
                width=2,
                height=2,
                duration_ms=60,
            ),
            takumi_py.RawAnimationFrame(
                data=b"\x00\xff\x00\xff" * 4,
                width=2,
                height=2,
                duration_ms=60,
            ),
        )
        assert (await api.encode_frames(raw_frames, format="gif")).startswith(b"GIF89a")
    finally:
        await state.aclose()


async def test_takumi_register_font_file_real_native() -> None:
    font_path = next(
        (candidate for candidate in _FONT_CANDIDATES if candidate.is_file()),
        None,
    )
    if font_path is None:
        pytest.skip("No standard system font is available for the Takumi font smoke.")

    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    api = TakumiAPIAdapter(state)
    try:
        families = await api.register_font_file(font_path, name="Htmlrender Smoke")
        assert families == ("Htmlrender Smoke",)
        assert api.registered_font_families == families

        rendered = await api.render_html(
            '<div style="font-family: Htmlrender Smoke;font-size: 12px">Smoke</div>',
            width=80,
            height=20,
        )
        assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        await state.aclose()
