"""Entari-only metadata, configuration, and service registration."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

from arclet.entari import add_service, local_data, metadata, plugin_config
from arclet.entari.plugin import PluginRole

from entari_plugin_htmlrender.providers.sdk import PLAYWRIGHT_PROVIDER_ID

from ._service import HtmlRenderService as _HtmlRenderService
from .composition import compose_runtime
from .config import RenderSettings

if TYPE_CHECKING:
    from .contracts import HtmlRenderService


def _distribution_version() -> str | None:
    try:
        return version("entari-plugin-htmlrender")
    except PackageNotFoundError:
        return None


def _apply_entari_defaults(settings: RenderSettings) -> RenderSettings:
    """Resolve host-owned defaults without leaking Entari into providers."""
    if settings.provider != PLAYWRIGHT_PROVIDER_ID:
        return settings
    provider_config = dict(settings.provider_config)
    if provider_config.get("storage_path") is not None:
        return settings
    provider_config["storage_path"] = (
        local_data.get_cache_dir("htmlrender") / "playwright"
    )
    return settings.model_copy(update={"provider_config": provider_config})


def register_plugin() -> HtmlRenderService:
    """Declare and compose the plugin inside an active Entari loader context."""
    metadata(
        name="HTMLRender",
        role=PluginRole.LIBRARY,
        author=[{"name": "kexue", "email": "x@kexue-cloud.cn"}],
        version=_distribution_version(),
        license="MIT",
        urls={
            "homepage": "https://github.com/kexue-z/entari-plugin-htmlrender",
            "issues": "https://github.com/kexue-z/entari-plugin-htmlrender/issues",
        },
        description=(
            "Provider-neutral HTML, Markdown, and template rendering with "
            "typed raster capabilities."
        ),
        config=RenderSettings,
    )
    settings = _apply_entari_defaults(plugin_config(RenderSettings))
    plan = compose_runtime(settings)
    runtime = plan.build_runtime()
    return add_service(
        _HtmlRenderService(
            runtime,
            settings,
            hosted_asset_server=plan.hosted_asset_server,
        )
    )


__all__ = ["register_plugin"]
