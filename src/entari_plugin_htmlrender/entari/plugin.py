"""Entari-only metadata, configuration, and service registration."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, cast

from arclet.entari import add_service, local_data, metadata, plugin_config
from arclet.entari.plugin import PluginRole

from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.providers.sdk import PLAYWRIGHT_PROVIDER_ID

from .service import HtmlRenderService

if TYPE_CHECKING:
    from launart import Service


def _distribution_version() -> str | None:
    try:
        return version("entari-plugin-htmlrender")
    except PackageNotFoundError:
        return None


def _apply_entari_defaults(config: HtmlRenderConfig) -> HtmlRenderConfig:
    """Resolve host-owned paths before framework-neutral composition."""
    if config.provider != PLAYWRIGHT_PROVIDER_ID:
        return config
    provider_config = dict(config.provider_config)
    if provider_config.get("storage_path") is not None:
        return config
    provider_config["storage_path"] = (
        local_data.get_cache_dir("htmlrender") / "playwright"
    )
    return config.model_copy(update={"provider_config": provider_config})


def register_plugin() -> HtmlRenderService:
    """Declare and compose HTMLRender inside an active Entari loader context."""
    metadata(
        name="HTMLRender",
        role=PluginRole.LIBRARY,
        author=[{"name": "Tacrolimus", "email": "balconyjh@gmail.com"}],
        version=_distribution_version(),
        license="MIT",
        urls={
            "homepage": "https://github.com/entanex/entari-plugin-htmlrender",
            "issues": "https://github.com/entanex/entari-plugin-htmlrender/issues",
        },
        description=(
            "Provider-neutral HTML, Markdown, and template rasterization with "
            "typed caller contracts."
        ),
        config=HtmlRenderConfig,
    )
    config = _apply_entari_defaults(plugin_config(HtmlRenderConfig))
    plan = build_runtime_plan(config)
    service = HtmlRenderService(
        plan.build_runtime(),
        config,
        hosted_asset_server=plan.hosted_asset_server,
    )
    add_service(cast("Service", service))
    return service


__all__ = ["register_plugin"]
