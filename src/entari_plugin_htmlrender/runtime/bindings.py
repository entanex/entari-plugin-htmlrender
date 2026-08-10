"""Private immutable bindings for the default renderer implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from entari_plugin_htmlrender.rendering.models import RenderOperation

if TYPE_CHECKING:
    from .use_cases import (
        _RasterizeHtml,
        _RasterizeMarkdown,
        _RasterizePrepared,
        _RasterizeTemplate,
        _RasterizeText,
    )


@dataclass(frozen=True, slots=True)
class _HtmlRendererBindings:
    rasterize_html: _RasterizeHtml | None = None
    rasterize_text: _RasterizeText | None = None
    rasterize_markdown: _RasterizeMarkdown | None = None
    rasterize_template: _RasterizeTemplate | None = None
    rasterize_prepared: _RasterizePrepared | None = None

    def supported_operations(self) -> frozenset[RenderOperation]:
        operations: set[RenderOperation] = set()
        if self.rasterize_html is not None:
            operations.add(RenderOperation.HTML_TO_IMAGE)
        if self.rasterize_text is not None:
            operations.add(RenderOperation.TEXT_TO_IMAGE)
        if self.rasterize_markdown is not None:
            operations.add(RenderOperation.MARKDOWN_TO_IMAGE)
        if self.rasterize_template is not None:
            operations.add(RenderOperation.TEMPLATE_TO_IMAGE)
        if self.rasterize_prepared is not None:
            operations.add(RenderOperation.PREPARED_HTML_TO_IMAGE)
        return frozenset(operations)


__all__: list[str] = []
