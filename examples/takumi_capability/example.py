"""Lease the managed Takumi API for provider-specific rendering."""

from __future__ import annotations

from html import escape

from entari_plugin_htmlrender import RuntimeSource, resolve_runtime

CARD_STYLE = """
body { margin: 0; background: #111827; color: #f9fafb; font-family: sans-serif; }
.card { margin: 24px; padding: 28px; border: 2px solid #8b5cf6; }
.title { font-size: 32px; font-weight: 700; }
.subtitle { margin-top: 12px; color: #c4b5fd; font-size: 18px; }
"""


async def render_takumi_card(runtime: RuntimeSource, title: str) -> bytes:
    html = (
        '<div class="card">'
        f'<div class="title">{escape(title)}</div>'
        '<div class="subtitle">Rendered through a leased native extension</div>'
        "</div>"
    )
    takumi = resolve_runtime(runtime).extensions.takumi
    async with takumi.api() as api:
        return await api.render_html(
            html,
            stylesheets=(CARD_STYLE,),
            width=640,
            height=240,
            device_pixel_ratio=1.0,
        )
