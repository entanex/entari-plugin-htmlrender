"""Static probes for the public first-party capability completion chain."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from typing_extensions import assert_type

from entari_plugin_htmlrender.capabilities import (
    PlaywrightCapability,
    TakumiCapability,
    TakumiSession,
)
from entari_plugin_htmlrender.graphics import GraphicsRenderer

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page
    from takumi_py import Renderer as TakumiRenderer

    from entari_plugin_htmlrender.runtime import RenderRuntime


async def _probe(runtime: RenderRuntime) -> None:
    playwright = assert_type(
        runtime.capabilities.playwright,
        PlaywrightCapability,
    )
    async with playwright.lease_page(
        viewport={"width": 800, "height": 600}
    ) as native_page:
        page = cast("Page", native_page)
        await page.goto("https://example.com")
        assert_type(await page.locator("main").screenshot(type="png"), bytes)

    async with playwright.lease_browser() as native_browser:
        browser = cast("Browser", native_browser)
        await browser.new_context(locale="zh-CN")

    takumi = assert_type(runtime.capabilities.takumi, TakumiCapability)
    async with takumi.lease_session() as session:
        assert_type(session, TakumiSession)
        assert_type(await session.render_html("<strong>Hello</strong>"), bytes)

    async with takumi.lease_native_renderer() as native_renderer:
        renderer = cast("TakumiRenderer", native_renderer)
        renderer.render_node({"type": "container"}, width=320, height=180)

    assert_type(runtime.graphics, GraphicsRenderer)
