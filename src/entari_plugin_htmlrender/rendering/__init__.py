"""Rendering contracts, artifacts, operation identities, and advanced ports."""

from entari_plugin_htmlrender.errors import (
    HtmlRenderError as HtmlRenderError,
)
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError as InvalidRenderInputError,
)
from entari_plugin_htmlrender.errors import (
    RenderTimeoutError as RenderTimeoutError,
)
from entari_plugin_htmlrender.errors import (
    RuntimeUnavailableError as RuntimeUnavailableError,
)
from entari_plugin_htmlrender.errors import (
    UnsupportedOperationError as UnsupportedOperationError,
)
from entari_plugin_htmlrender.resources.config import (
    ResourceMaterializationPolicy as ResourceMaterializationPolicy,
)

from .admission import OperationAdmissionGate as OperationAdmissionGate
from .artifacts import RenderedHtml as RenderedHtml
from .artifacts import RenderedImage as RenderedImage
from .capabilities import CapabilityCatalog as CapabilityCatalog
from .capabilities import CapabilityKey as CapabilityKey
from .contracts import HtmlRenderer as HtmlRenderer
from .contracts import TemplateRenderer as TemplateRenderer
from .models import RenderOperation as RenderOperation
from .observers import NoopCacheObserver as NoopCacheObserver
from .observers import NoopOperationObserver as NoopOperationObserver
from .ports import CacheObserver as CacheObserver
from .ports import OperationAdmission as OperationAdmission
from .ports import OperationObserver as OperationObserver
from .ports import PreparedHtmlExecutor as PreparedHtmlExecutor
from .ports import RuntimeLifecycle as RuntimeLifecycle

__all__ = [
    "CacheObserver",
    "CapabilityCatalog",
    "CapabilityKey",
    "HtmlRenderError",
    "HtmlRenderer",
    "InvalidRenderInputError",
    "NoopCacheObserver",
    "NoopOperationObserver",
    "OperationAdmission",
    "OperationAdmissionGate",
    "OperationObserver",
    "PreparedHtmlExecutor",
    "RenderOperation",
    "RenderTimeoutError",
    "RenderedHtml",
    "RenderedImage",
    "ResourceMaterializationPolicy",
    "RuntimeLifecycle",
    "RuntimeUnavailableError",
    "TemplateRenderer",
    "UnsupportedOperationError",
]
