"""Lease the managed Takumi API for provider-specific rendering."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entari_plugin_htmlrender.capabilities import TakumiCapability

CARD_STYLE = """
body { margin: 0; background: #111827; color: #f9fafb; font-family: sans-serif; }
.card { margin: 24px; padding: 28px; border: 2px solid #8b5cf6; }
.title { font-size: 32px; font-weight: 700; }
.subtitle { margin-top: 12px; color: #c4b5fd; font-size: 18px; }
"""


async def render_takumi_card(takumi: TakumiCapability, title: str) -> str:
    html = (
        '<div class="card">'
        f'<div class="title">{escape(title)}</div>'
        '<div class="subtitle">Rendered through a managed capability lease</div>'
        "</div>"
    )
    async with takumi.lease_session() as session:
        return await session.render_svg_html(
            html,
            stylesheets=(CARD_STYLE,),
            width=640,
            height=240,
        )
