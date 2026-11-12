"""使用 skia-python 的绘图接口生成 Profile 卡片。"""

from __future__ import annotations

from typing import TYPE_CHECKING

# skia-python 只提供二进制扩展，没有类型存根。
import skia  # ty: ignore[unresolved-import]

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.skia import SkiaCanvas


def _paint(red: int, green: int, blue: int, *, alpha: int = 255) -> skia.Paint:
    paint = skia.Paint(AntiAlias=True)
    paint.setColor(skia.ColorSetARGB(alpha, red, green, blue))
    return paint


def _rect(x: float, y: float, width: float, height: float) -> skia.Rect:
    return skia.Rect.MakeXYWH(x, y, width, height)


def _text(
    canvas: SkiaCanvas,
    value: str,
    x: float,
    y: float,
    *,
    size: float,
    paint: skia.Paint,
) -> None:
    blob = skia.TextBlob.MakeFromString(
        value,
        skia.Font(skia.Typeface.MakeFromName(None), size),
    )
    canvas.canvas.drawTextBlob(blob, x, y, paint)


def draw(canvas: SkiaCanvas, data: Mapping[str, object]) -> None:
    """在 Skia 画布上绘制卡片。"""
    title = str(data.get("title", "Profile"))
    subtitle = str(data.get("subtitle", "使用 Skia 绘图"))
    accent = _paint(139, 92, 246)
    surface = _paint(30, 41, 59)
    foreground = _paint(249, 250, 251)
    muted = _paint(196, 181, 253)

    canvas.canvas.drawRoundRect(
        _rect(40, 32, canvas.width - 80, canvas.height - 64),
        24,
        24,
        surface,
    )

    outline = _paint(139, 92, 246)
    outline.setStyle(skia.Paint.kStroke_Style)
    outline.setStrokeWidth(2)
    canvas.canvas.drawRoundRect(
        _rect(40, 32, canvas.width - 80, canvas.height - 64),
        24,
        24,
        outline,
    )

    canvas.canvas.drawCircle(52, 52, 4, accent)
    _text(canvas, title, 72, 78, size=32, paint=foreground)
    _text(canvas, subtitle, 72, 121, size=20, paint=muted)

    separator = skia.Paint(AntiAlias=False)
    separator.setColor(skia.ColorSetARGB(255, 71, 85, 105))
    separator.setStrokeWidth(1)
    canvas.canvas.drawLine(72, 175, canvas.width - 72, 175, separator)

    canvas.canvas.drawCircle(canvas.width - 108, 96, 26, _paint(56, 189, 248))
    canvas.canvas.drawCircle(canvas.width - 108, 96, 12, _paint(45, 212, 191))
