"""Caller-first template rendering with an Entari-injected service."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from entari_plugin_htmlrender import (
    RasterOptions,
    RenderedImage,
    TemplateRef,
)

if TYPE_CHECKING:
    from entari_plugin_htmlrender.entari import HtmlRenderService

TEMPLATE_DIR = Path(__file__).with_name("templates")
PROFILE_TEMPLATE = TemplateRef(TEMPLATE_DIR, "profile.html")


async def render_profile(
    service: HtmlRenderService,
    username: str,
) -> RenderedImage:
    """Render a profile from a service injected by an Entari handler."""
    return await service.renderer.rasterize_template(
        PROFILE_TEMPLATE,
        {
            "avatar_text": username[:1].upper() or "?",
            "username": username,
            "level": 42,
            "signature": "Talk is cheap, show me the code.",
            "stats": (
                {"label": "Days", "value": "128"},
                {"label": "Plugins", "value": "15"},
                {"label": "Messages", "value": "3.2k"},
            ),
        },
        raster=RasterOptions(
            width=440,
            height=None,
            device_pixel_ratio=1.0,
        ),
    )


async def render_plain_text(
    service: HtmlRenderService,
    content: str,
) -> RenderedImage:
    return await service.renderer.rasterize_text(
        content,
        raster=RasterOptions(width=600, device_pixel_ratio=1.0),
    )
