"""Profile card composed from the package's shared helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .colors import card, marker, palette, text

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.pillow import PillowCanvas


def draw(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
    """Draw a profile named by the caller."""
    name = str(data.get("name", "Ada"))
    title = str(data.get("title", "Shared profile"))
    subtitle = str(data.get("subtitle", "Styles from colors.py"))

    inner = card(canvas)
    marker(canvas)
    text(
        canvas,
        title,
        (inner[0], inner[1]),
        size=32,
        color=palette["foreground"],
    )
    text(
        canvas,
        name,
        (inner[0], inner[1] + 48),
        size=24,
        color=palette["secondary"],
    )
    text(
        canvas,
        subtitle,
        (inner[0], inner[1] + 88),
        size=20,
        color=palette["muted"],
    )
    canvas.draw.line(
        (inner[0], inner[1] + 132, inner[2], inner[1] + 132),
        fill=palette["rule"],
        width=1,
    )
