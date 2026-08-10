"""Caller-first contracts and values for HTMLRender.

The package root deliberately excludes runtime composition, Provider SDK,
adapter, and Entari lifecycle types.  Ordinary code receives the contracts
exported here through constructor or host injection.
"""

from importlib.metadata import PackageNotFoundError, version

from entari_plugin_htmlrender.errors import (
    CapabilityUnavailableError as CapabilityUnavailableError,
)
from entari_plugin_htmlrender.errors import HtmlRenderError as HtmlRenderError
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError as InvalidRenderInputError,
)
from entari_plugin_htmlrender.errors import ProviderError as ProviderError
from entari_plugin_htmlrender.errors import (
    RenderOutputLimitError as RenderOutputLimitError,
)
from entari_plugin_htmlrender.errors import (
    RenderTimeoutError as RenderTimeoutError,
)
from entari_plugin_htmlrender.errors import ResourceError as ResourceError
from entari_plugin_htmlrender.errors import (
    RuntimeUnavailableError as RuntimeUnavailableError,
)
from entari_plugin_htmlrender.errors import (
    UnsupportedOperationError as UnsupportedOperationError,
)
from entari_plugin_htmlrender.preparation.html import parse_html as parse_html
from entari_plugin_htmlrender.preparation.models import (
    DocumentBase as DocumentBase,
)
from entari_plugin_htmlrender.preparation.models import (
    DocumentRequirement as DocumentRequirement,
)
from entari_plugin_htmlrender.preparation.models import (
    PreparedAsset as PreparedAsset,
)
from entari_plugin_htmlrender.preparation.models import (
    PreparedHtml as PreparedHtml,
)
from entari_plugin_htmlrender.preparation.models import (
    PreparedStylesheet as PreparedStylesheet,
)
from entari_plugin_htmlrender.preparation.models import (
    RasterOptions as RasterOptions,
)
from entari_plugin_htmlrender.preparation.models import TemplateRef as TemplateRef
from entari_plugin_htmlrender.raster import RasterImageFormat as RasterImageFormat
from entari_plugin_htmlrender.rendering.artifacts import (
    RenderedHtml as RenderedHtml,
)
from entari_plugin_htmlrender.rendering.artifacts import (
    RenderedImage as RenderedImage,
)
from entari_plugin_htmlrender.rendering.contracts import (
    HtmlRenderer as HtmlRenderer,
)
from entari_plugin_htmlrender.rendering.contracts import (
    TemplateRenderer as TemplateRenderer,
)
from entari_plugin_htmlrender.rendering.models import (
    RenderOperation as RenderOperation,
)
from entari_plugin_htmlrender.resources.config import (
    ResourceMaterializationPolicy as ResourceMaterializationPolicy,
)

try:
    __version__ = version("entari-plugin-htmlrender")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
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
]


if "__plugin__" in globals():
    from entari_plugin_htmlrender.entari.plugin import (
        register_plugin as _register_plugin,
    )

    _register_plugin()
    del _register_plugin
