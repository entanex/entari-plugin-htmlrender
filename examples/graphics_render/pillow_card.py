"""使用 Pillow 的绘图接口生成 Profile 卡片。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import ImageFont

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.pillow import PillowCanvas


def draw(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
    """在 Pillow 画布上绘制卡片。"""
    title = str(data.get("title", "Profile"))
    subtitle = str(data.get("subtitle", "使用 Pillow 绘图"))
    accent = (139, 92, 246, 255)
    surface = (30, 41, 59, 255)
    foreground = (249, 250, 251, 255)
    muted = (196, 181, 253, 255)

    card = (40, 32, canvas.width - 40, canvas.height - 32)
    canvas.draw.rounded_rectangle(
        card,
        radius=24,
        fill=surface,
        outline=accent,
        width=2,
    )
    canvas.draw.ellipse((48, 48, 56, 56), fill=accent)
    canvas.draw.text(
        (72, 66),
        title,
        font=ImageFont.load_default(size=32),
        fill=foreground,
    )
    canvas.draw.text(
        (72, 118),
        subtitle,
        font=ImageFont.load_default(size=20),
        fill=muted,
    )
    canvas.draw.line(
        (72, 175, canvas.width - 72, 175),
        fill=(71, 85, 105, 255),
        width=1,
    )
