"""Badge card using the same helper instance as the profile drawing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .colors import card, marker, palette, text

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.pillow import PillowCanvas


def draw(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
    """Draw a compact status badge."""
    label = str(data.get("label", "Shared badge"))
    detail = str(data.get("detail", "Same palette instance"))
    accent = palette["secondary"]

    inner = card(canvas, accent=accent)
    marker(canvas)
    text(
        canvas,
        label,
        (inner[0], inner[1]),
        size=32,
        color=palette["foreground"],
    )
    text(
        canvas,
        detail,
        (inner[0], inner[1] + 60),
        size=20,
        color=palette["muted"],
    )
    canvas.draw.ellipse(
        (inner[2] - 44, inner[1] + 12, inner[2], inner[1] + 56),
        fill=accent,
    )
