"""Rendering-boundary errors re-exported from the single public taxonomy."""

from entari_plugin_htmlrender.errors import (
    CapabilityUnavailableError as CapabilityUnavailableError,
)
from entari_plugin_htmlrender.errors import HtmlRenderError as HtmlRenderError
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError as InvalidRenderInputError,
)
from entari_plugin_htmlrender.errors import (
    ProviderExecutionError as ProviderExecutionError,
)
from entari_plugin_htmlrender.errors import (
    ProviderLifecycleError as ProviderLifecycleError,
)
from entari_plugin_htmlrender.errors import (
    RenderTimeoutError as RenderTimeoutError,
)
from entari_plugin_htmlrender.errors import (
    RuntimeUnavailableError as RuntimeUnavailableError,
)
from entari_plugin_htmlrender.errors import (
    UnsupportedDocumentFeatureError as UnsupportedDocumentFeatureError,
)
from entari_plugin_htmlrender.errors import (
    UnsupportedOperationError as UnsupportedOperationError,
)
from entari_plugin_htmlrender.errors import (
    UnsupportedRasterOptionError as UnsupportedRasterOptionError,
)

__all__ = [
    "CapabilityUnavailableError",
    "HtmlRenderError",
    "InvalidRenderInputError",
    "ProviderExecutionError",
    "ProviderLifecycleError",
    "RenderTimeoutError",
    "RuntimeUnavailableError",
    "UnsupportedDocumentFeatureError",
    "UnsupportedOperationError",
    "UnsupportedRasterOptionError",
]
