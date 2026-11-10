"""Static probes for the public first-party capability completion chain."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, assert_type

from playwright.async_api import Browser, Page
from takumi_py import (
    AnimationScene,
    CompiledNode,
    CompiledStyleSheet,
    MeasuredNode,
    RawAnimationFrame,
)
from takumi_py import (
    Renderer as TakumiRenderer,
)

from entari_plugin_htmlrender.capabilities import (
    PlaywrightCapability,
    TakumiAPI,
    TakumiCapability,
    TakumiCompiledDocument,
    TakumiSession,
)
from entari_plugin_htmlrender.graphics import GraphicsRenderer
from entari_plugin_htmlrender.resources import ResourceResolution

if TYPE_CHECKING:
    from entari_plugin_htmlrender.runtime import RenderRuntime


async def _probe(runtime: RenderRuntime) -> None:
    playwright = assert_type(
        runtime.capabilities.playwright,
        PlaywrightCapability,
    )
    async with playwright.lease_page(viewport={"width": 800, "height": 600}) as page:
        assert_type(page, Page)
        await page.goto("https://example.com")
        assert_type(await page.locator("main").screenshot(type="png"), bytes)

    async with playwright.lease_browser() as browser:
        assert_type(browser, Browser)
        await browser.new_context(locale="zh-CN")

    takumi = assert_type(runtime.capabilities.takumi, TakumiCapability)
    async with takumi.lease_session() as session:
        assert_type(session, TakumiSession)
        assert_type(await session.render_html("<strong>Hello</strong>"), bytes)

    async with takumi.lease_api() as api:
        assert_type(api, TakumiAPI)

        document = assert_type(
            await api.compile_html(
                '<img src="memory:avatar"><div class="card">Hello</div>',
                stylesheets=(".card { color: red }",),
                images=[("memory:avatar", b"image")],
            ),
            TakumiCompiledDocument,
        )
        assert_type(document.node, CompiledNode)
        assert_type(document.stylesheets, tuple[CompiledStyleSheet, ...])
        assert_type(await api.render_compiled(document), bytes)
        assert_type(await api.measure_compiled(document), MeasuredNode)
        assert_type(await api.render_svg_compiled(document), str)

        node = assert_type(
            await api.compile_node({"type": "container"}, validate=True),
            CompiledNode,
        )
        keyframes = assert_type(
            await api.compile_keyframes(
                {
                    "fade": {
                        "from": {"opacity": 0},
                        "to": {"opacity": 1},
                    }
                }
            ),
            CompiledStyleSheet,
        )
        assert_type(
            await api.compile_stylesheet("div { color: red }"), CompiledStyleSheet
        )
        assert_type(await api.render_node({"type": "container"}), bytes)
        assert_type(await api.measure_node({"type": "container"}), MeasuredNode)
        assert_type(await api.render_svg_node({"type": "container"}), str)

        scenes = [AnimationScene(node=node, duration_ms=100)]
        assert_type(await api.render_animation(scenes), bytes)
        assert_type(await api.render_sequence_at_time(scenes, 50), bytes)
        frames = [
            RawAnimationFrame(
                data=b"\x00" * 16,
                width=2,
                height=2,
                duration_ms=100,
            )
        ]
        assert_type(await api.encode_frames(frames), bytes)
        assert_type(await api.render_html("<strong>Hello</strong>"), bytes)
        assert_type(await api.measure_html("<strong>Hello</strong>"), MeasuredNode)
        assert_type(await api.render_svg_html("<strong>Hello</strong>"), str)
        assert_type(await api.register_font(b"font"), tuple[str, ...])
        assert_type(await api.register_fonts([b"font"]), tuple[str, ...])
        assert_type(keyframes, CompiledStyleSheet)

    async with takumi.lease_native_renderer() as renderer:
        assert_type(renderer, TakumiRenderer)
        renderer.render_node({"type": "container"}, width=320, height=180)

    assert_type(runtime.capabilities.pillow, GraphicsRenderer)
    assert_type(runtime.capabilities.skia, GraphicsRenderer)
    assert_type(runtime.graphics, GraphicsRenderer)

    variables = assert_type(
        await runtime.resources.resolve_template_vars({"asset": b"image"}),
        ResourceResolution[dict[str, object]],
    )
    assert_type(
        variables.request_headers_by_url,
        Mapping[str, Mapping[str, str]],
    )
    assert_type(
        await runtime.resources.to_resource_url(b"image"),
        ResourceResolution[str],
    )
    assert_type(
        await runtime.resources.resolve_url_tokens(("style.css",)),
        ResourceResolution[list[str]],
    )
