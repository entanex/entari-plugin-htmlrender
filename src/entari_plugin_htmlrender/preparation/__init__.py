"""Backend-neutral preparation domain and pure HTML canonicalization."""

from .html import parse_html
from .models import (
    DocumentBase,
    DocumentRequirement,
    DocumentStructureSnapshot,
    PreparedAsset,
    PreparedHtml,
    PreparedStylesheet,
    RasterOptions,
    TemplateRef,
)
from .service import DefaultHtmlPreparer, HtmlPreparer

__all__ = (
    "DefaultHtmlPreparer",
    "DocumentBase",
    "DocumentRequirement",
    "DocumentStructureSnapshot",
    "HtmlPreparer",
    "PreparedAsset",
    "PreparedHtml",
    "PreparedStylesheet",
    "RasterOptions",
    "TemplateRef",
    "parse_html",
)
