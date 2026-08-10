"""Explicit Entari integration surface for HTMLRender."""

from entari_plugin_htmlrender.config import HtmlRenderConfig as HtmlRenderConfig
from entari_plugin_htmlrender.config import (
    RuntimeStartupPolicy as RuntimeStartupPolicy,
)

from .service import HtmlRenderService as HtmlRenderService

__all__ = [
    "HtmlRenderConfig",
    "HtmlRenderService",
    "RuntimeStartupPolicy",
]
