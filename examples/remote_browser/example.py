"""Remote Playwright operations without coupling to a message adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from entari_plugin_htmlrender import RasterOptions

if TYPE_CHECKING:
    from entari_plugin_htmlrender import HtmlRenderer, RenderedImage
    from entari_plugin_htmlrender.capabilities import PlaywrightCapability


async def screenshot_url(
    playwright: PlaywrightCapability,
    url: str,
    *,
    full_page: bool = True,
) -> bytes:
    """Capture a trusted URL through the configured Playwright endpoint."""
    async with playwright.lease_page(viewport={"width": 1280, "height": 800}) as page:
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        return await page.screenshot(full_page=full_page, type="png")


async def render_remote_markdown(
    renderer: HtmlRenderer,
    markdown: str,
) -> RenderedImage:
    return await renderer.rasterize_markdown(
        markdown,
        raster=RasterOptions(width=720),
    )
