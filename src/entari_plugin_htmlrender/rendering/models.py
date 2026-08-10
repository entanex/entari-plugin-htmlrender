"""Caller-facing rendering identities."""

from __future__ import annotations

from enum import Enum


class RenderOperation(str, Enum):
    """Stable domain identities for renderer operations.

    Values describe both the input domain and output artifact. They are not
    coupled to Python method names, so an implementation can evolve without
    changing capability identity.
    """

    HTML_TO_IMAGE = "html_to_image"
    TEXT_TO_IMAGE = "text_to_image"
    MARKDOWN_TO_IMAGE = "markdown_to_image"
    TEMPLATE_TO_IMAGE = "template_to_image"
    PREPARED_HTML_TO_IMAGE = "prepared_html_to_image"
    RASTER_SCENE_TO_IMAGE = "raster_scene_to_image"
    TEMPLATE_TO_HTML = "template_to_html"


__all__ = ["RenderOperation"]
