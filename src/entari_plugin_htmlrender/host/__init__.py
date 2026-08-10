"""Entari-facing configuration models.

Composition and service registration live in their explicit submodules so
importing this package does not register an Entari plugin or build a runtime.
"""

from importlib import import_module
from typing import TYPE_CHECKING, cast

from .config import GraphicsSettings as GraphicsSettings
from .config import RenderSettings as RenderSettings
from .config import RenderStartupMode as RenderStartupMode

if TYPE_CHECKING:
    from .contracts import HtmlRenderService as HtmlRenderService


def __getattr__(name: str) -> object:
    """Load the public Service type only when a host asks for it."""
    if name == "HtmlRenderService":
        service_module = import_module(f"{__name__}._service")
        return cast("object", vars(service_module)[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "GraphicsSettings",
    "HtmlRenderService",
    "RenderSettings",
    "RenderStartupMode",
]
