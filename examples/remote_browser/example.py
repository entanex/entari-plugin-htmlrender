"""Remote Playwright operations without coupling to a message adapter."""

from __future__ import annotations

from entari_plugin_htmlrender import (
    RenderedImage,
    RuntimeSource,
    render_markdown,
    resolve_runtime,
)


async def screenshot_url(
    runtime: RuntimeSource,
    url: str,
    *,
    full_page: bool = True,
) -> bytes:
    """Capture a trusted URL through the configured Playwright endpoint."""
    playwright = resolve_runtime(runtime).extensions.playwright
    async with playwright.page(viewport={"width": 1280, "height": 800}) as page:
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        return await page.screenshot(full_page=full_page, type="png")


async def render_remote_markdown(
    runtime: RuntimeSource,
    markdown: str,
) -> RenderedImage:
    return await render_markdown(markdown, width=720, runtime=runtime)
