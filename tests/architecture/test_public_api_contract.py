"""Initial public API contract for entari-plugin-htmlrender."""

from __future__ import annotations

from importlib.metadata import version
from typing import get_type_hints

import entari_plugin_htmlrender as htmlrender
from entari_plugin_htmlrender import HtmlRenderer, TemplateRenderer

_EXPECTED_ROOT_EXPORTS = {
    "CapabilityUnavailableError",
    "DocumentBase",
    "DocumentRequirement",
    "HtmlRenderError",
    "HtmlRenderer",
    "InvalidRenderInputError",
    "PreparedAsset",
    "PreparedHtml",
    "PreparedStylesheet",
    "ProviderError",
    "RasterImageFormat",
    "RasterOptions",
    "RenderOperation",
    "RenderOutputLimitError",
    "RenderTimeoutError",
    "RenderedHtml",
    "RenderedImage",
    "ResourceError",
    "ResourceMaterializationPolicy",
    "RuntimeUnavailableError",
    "TemplateRef",
    "TemplateRenderer",
    "UnsupportedOperationError",
    "__version__",
    "parse_html",
}


def test_root_exports_only_the_curated_caller_surface() -> None:
    assert set(htmlrender.__all__) == _EXPECTED_ROOT_EXPORTS


def test_source_version_matches_distribution_metadata() -> None:
    assert htmlrender.__version__ == version("entari-plugin-htmlrender")


def test_caller_protocol_annotations_are_runtime_resolvable() -> None:
    for method in (
        HtmlRenderer.rasterize_html,
        HtmlRenderer.rasterize_text,
        HtmlRenderer.rasterize_markdown,
        HtmlRenderer.rasterize_template,
        HtmlRenderer.rasterize_prepared,
        TemplateRenderer.render,
    ):
        annotations = get_type_hints(method)
        assert "return" in annotations
