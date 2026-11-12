"""Shared palette and card primitives for the example drawings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import ImageFont

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.pillow import PillowCanvas

RGBA = tuple[int, int, int, int]

# This module-level value is computed once and shared by both drawings.
palette: Mapping[str, RGBA] = {
    "page": (15, 23, 42, 255),
    "surface": (30, 41, 59, 255),
    "accent": (139, 92, 246, 255),
    "secondary": (56, 189, 248, 255),
    "foreground": (249, 250, 251, 255),
    "muted": (196, 181, 253, 255),
    "rule": (71, 85, 105, 255),
}


def card(
    canvas: PillowCanvas,
    *,
    accent: RGBA | None = None,
) -> tuple[int, int, int, int]:
    """Draw the shared card background and return its padding box."""
    outer = (40, 32, canvas.width - 40, canvas.height - 32)
    inner = (72, 72, canvas.width - 72, canvas.height - 72)
    canvas.draw.rounded_rectangle(
        outer,
        radius=24,
        fill=palette["surface"],
        outline=accent or palette["accent"],
        width=2,
    )
    return inner


def marker(canvas: PillowCanvas) -> None:
    """Draw the shared accent marker."""
    canvas.draw.ellipse((48, 48, 56, 56), fill=palette["accent"])


def text(
    canvas: PillowCanvas,
    value: str,
    position: tuple[int, int],
    *,
    size: int,
    color: RGBA,
) -> None:
    """Draw simple UTF-8 text with Pillow's bundled fallback font."""
    canvas.draw.text(
        position,
        value,
        font=ImageFont.load_default(size=size),
        fill=color,
    )
