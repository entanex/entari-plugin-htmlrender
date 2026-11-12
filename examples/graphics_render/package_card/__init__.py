"""A complete Pillow drawing whose only source file is this initializer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.pillow import PillowCanvas


def draw(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
    """Draw directly from the package entrypoint."""
    canvas.image.paste((30, 41, 59, 255), (0, 0, canvas.width, canvas.height))
    canvas.draw.text(
        (24, 24),
        str(data.get("title", "Hello, Entari")),
        fill=(255, 255, 255, 255),
    )
