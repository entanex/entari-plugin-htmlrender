"""Render Markdown with structurally detected Arithmatex expressions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import markdown
from markdown.treeprocessors import Treeprocessor
from pymdownx.arithmatex import ArithmatexExtension

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

_ARITHMATEX_ATTRIBUTE = "data-htmlrender-arithmatex"


@dataclass(frozen=True, slots=True)
class MarkdownRender:
    html: str
    has_math: bool


class _ArithmatexObserver(Treeprocessor):
    """Mark only containers created by the Arithmatex extension."""

    def __init__(self) -> None:
        super().__init__()
        self.has_math = False

    def run(self, root: Element) -> None:
        wrappers = (("span", "\\(", "\\)"), ("div", "\\[", "\\]"))
        for tag, opening, closing in wrappers:
            for element in root.iter(tag):
                if "arithmatex" not in element.get("class", "").split():
                    continue
                text = element.text or ""
                if not (text.startswith(opening) and text.endswith(closing)):
                    continue
                element.set(_ARITHMATEX_ATTRIBUTE, "")
                self.has_math = True


def render_markdown(source: str) -> MarkdownRender:
    """Render Markdown and report math from the generated element tree."""

    parser = markdown.Markdown(
        extensions=[
            "pymdownx.tasklist",
            "tables",
            "fenced_code",
            "codehilite",
            ArithmatexExtension(
                generic=True,
                smart_dollar=True,
                block_syntax=["dollar", "square", "begin"],
                inline_syntax=["dollar", "round"],
            ),
            "pymdownx.tilde",
        ]
    )
    observer = _ArithmatexObserver()
    parser.treeprocessors.register(
        observer,
        "htmlrender-arithmatex-observer",
        0,
    )
    rendered = parser.convert(source)
    return MarkdownRender(html=rendered, has_math=observer.has_math)


__all__ = ["render_markdown"]
