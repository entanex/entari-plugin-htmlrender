"""Public library facade and conditional Entari composition entry point."""

from importlib.metadata import PackageNotFoundError, version

from entari_plugin_htmlrender.api import RuntimeResolver as RuntimeResolver
from entari_plugin_htmlrender.api import RuntimeSource as RuntimeSource
from entari_plugin_htmlrender.api import parse_html as parse_html
from entari_plugin_htmlrender.api import prepare_markdown as prepare_markdown
from entari_plugin_htmlrender.api import prepare_template as prepare_template
from entari_plugin_htmlrender.api import prepare_text as prepare_text
from entari_plugin_htmlrender.api import rasterize_html as rasterize_html
from entari_plugin_htmlrender.api import render_html as render_html
from entari_plugin_htmlrender.api import render_markdown as render_markdown
from entari_plugin_htmlrender.api import render_template as render_template
from entari_plugin_htmlrender.api import (
    render_template_html as render_template_html,
)
from entari_plugin_htmlrender.api import render_text as render_text
from entari_plugin_htmlrender.api import resolve_resource_url as resolve_resource_url
from entari_plugin_htmlrender.api import resolve_runtime as resolve_runtime
from entari_plugin_htmlrender.api import (
    resolve_template_vars as resolve_template_vars,
)
from entari_plugin_htmlrender.api import runtime_context as runtime_context
from entari_plugin_htmlrender.host.config import RenderSettings as RenderSettings
from entari_plugin_htmlrender.host.config import (
    RenderStartupMode as RenderStartupMode,
)
from entari_plugin_htmlrender.preparation import DocumentBase as DocumentBase
from entari_plugin_htmlrender.preparation import PreparedAsset as PreparedAsset
from entari_plugin_htmlrender.preparation import PreparedHtml as PreparedHtml
from entari_plugin_htmlrender.preparation import (
    PreparedStylesheet as PreparedStylesheet,
)
from entari_plugin_htmlrender.preparation import RasterOptions as RasterOptions
from entari_plugin_htmlrender.preparation import (
    RenderRequirement as RenderRequirement,
)
from entari_plugin_htmlrender.raster import RasterImageFormat as RasterImageFormat
from entari_plugin_htmlrender.rendering import (
    CapabilityUnavailable as CapabilityUnavailable,
)
from entari_plugin_htmlrender.rendering import ErrorCause as ErrorCause
from entari_plugin_htmlrender.rendering import (
    InvalidRenderRequest as InvalidRenderRequest,
)
from entari_plugin_htmlrender.rendering import PreparationError as PreparationError
from entari_plugin_htmlrender.rendering import (
    ProviderExecutionError as ProviderExecutionError,
)
from entari_plugin_htmlrender.rendering import (
    ProviderLifecycleError as ProviderLifecycleError,
)
from entari_plugin_htmlrender.rendering import ProviderNotFound as ProviderNotFound
from entari_plugin_htmlrender.rendering import (
    ProviderUnavailable as ProviderUnavailable,
)
from entari_plugin_htmlrender.rendering import (
    RasterizeHtmlRequest as RasterizeHtmlRequest,
)
from entari_plugin_htmlrender.rendering import RenderCommand as RenderCommand
from entari_plugin_htmlrender.rendering import RenderedHtml as RenderedHtml
from entari_plugin_htmlrender.rendering import RenderedImage as RenderedImage
from entari_plugin_htmlrender.rendering import RenderHtmlRequest as RenderHtmlRequest
from entari_plugin_htmlrender.rendering import (
    RenderingError as RenderingError,
)
from entari_plugin_htmlrender.rendering import (
    RenderMarkdownRequest as RenderMarkdownRequest,
)
from entari_plugin_htmlrender.rendering import (
    RenderTemplateHtmlRequest as RenderTemplateHtmlRequest,
)
from entari_plugin_htmlrender.rendering import (
    RenderTemplateRequest as RenderTemplateRequest,
)
from entari_plugin_htmlrender.rendering import RenderTextRequest as RenderTextRequest
from entari_plugin_htmlrender.rendering import ResourcePolicy as ResourcePolicy
from entari_plugin_htmlrender.rendering import (
    ResourceResolutionError as ResourceResolutionError,
)
from entari_plugin_htmlrender.rendering import RuntimeNotBound as RuntimeNotBound
from entari_plugin_htmlrender.rendering import (
    UnsupportedRenderOption as UnsupportedRenderOption,
)
from entari_plugin_htmlrender.rendering import (
    UnsupportedRequirement as UnsupportedRequirement,
)
from entari_plugin_htmlrender.resources import (
    ResourceResolution as ResourceResolution,
)
from entari_plugin_htmlrender.runtime import HtmlRenderer as HtmlRenderer
from entari_plugin_htmlrender.runtime import RenderRuntime as RenderRuntime

try:
    __version__ = version("entari-plugin-htmlrender")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "CapabilityUnavailable",
    "DocumentBase",
    "ErrorCause",
    "HtmlRenderer",
    "InvalidRenderRequest",
    "PreparationError",
    "PreparedAsset",
    "PreparedHtml",
    "PreparedStylesheet",
    "ProviderExecutionError",
    "ProviderLifecycleError",
    "ProviderNotFound",
    "ProviderUnavailable",
    "RasterImageFormat",
    "RasterOptions",
    "RasterizeHtmlRequest",
    "RenderCommand",
    "RenderHtmlRequest",
    "RenderMarkdownRequest",
    "RenderRequirement",
    "RenderRuntime",
    "RenderSettings",
    "RenderStartupMode",
    "RenderTemplateHtmlRequest",
    "RenderTemplateRequest",
    "RenderTextRequest",
    "RenderedHtml",
    "RenderedImage",
    "RenderingError",
    "ResourcePolicy",
    "ResourceResolution",
    "ResourceResolutionError",
    "RuntimeNotBound",
    "RuntimeResolver",
    "RuntimeSource",
    "UnsupportedRenderOption",
    "UnsupportedRequirement",
    "parse_html",
    "prepare_markdown",
    "prepare_template",
    "prepare_text",
    "rasterize_html",
    "render_html",
    "render_markdown",
    "render_template",
    "render_template_html",
    "render_text",
    "resolve_resource_url",
    "resolve_runtime",
    "resolve_template_vars",
    "runtime_context",
]


if "__plugin__" in globals():
    from entari_plugin_htmlrender.host.registration import (
        register_plugin as _register_plugin,
    )

    _register_plugin()
    del _register_plugin
