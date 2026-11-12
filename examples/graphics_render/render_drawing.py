"""Render named drawings through the injected drawing contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from entari_plugin_htmlrender.graphics import (
    RasterEncodeOptions,
    RGBAColor,
)

if TYPE_CHECKING:
    from entari_plugin_htmlrender import RenderedImage
    from entari_plugin_htmlrender.graphics import DrawingRenderer


async def render_profile_card(drawings: DrawingRenderer) -> RenderedImage:
    """Render the drawing configured under the name ``profile``."""
    return await drawings.render(
        "profile",
        {
            "name": "Ada",
            "title": "Shared profile",
            "subtitle": "Styles from colors.py",
        },
        width=640,
        height=360,
        background=RGBAColor(15, 23, 42),
        output=RasterEncodeOptions(format="png"),
    )


async def render_badge_card(drawings: DrawingRenderer) -> RenderedImage:
    """Render the drawing configured under the name ``badge``."""
    return await drawings.render(
        "badge",
        {
            "label": "Shared badge",
            "detail": "Same palette instance",
        },
        width=640,
        height=360,
        background=RGBAColor(15, 23, 42),
        output=RasterEncodeOptions(format="png"),
    )
