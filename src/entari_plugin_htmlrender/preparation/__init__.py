"""Backend-neutral preparation domain and pure HTML canonicalization."""

from .html import parse_html
from .models import (
    DocumentBase,
    DocumentStructureSnapshot,
    PreparedAsset,
    PreparedHtml,
    PreparedStylesheet,
    RasterOptions,
    RenderRequirement,
)
from .service import DefaultHtmlPreparer, HtmlPreparer

__all__ = (
    "DefaultHtmlPreparer",
    "DocumentBase",
    "DocumentStructureSnapshot",
    "HtmlPreparer",
    "PreparedAsset",
    "PreparedHtml",
    "PreparedStylesheet",
    "RasterOptions",
    "RenderRequirement",
    "parse_html",
)
