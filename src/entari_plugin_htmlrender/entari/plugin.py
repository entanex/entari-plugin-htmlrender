"""Entari-only metadata, configuration, and service registration."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, cast

import anyio
from arclet.entari import (
    add_service,
    collect_disposes,
    local_data,
    metadata,
    plugin_config,
)
from arclet.entari.plugin import PluginRole, get_plugin, keeping
from arclet.entari.plugin.service import plugin_service
from creart import it
from launart import Launart

from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.providers.sdk import PLAYWRIGHT_PROVIDER_ID

from .drawing_plugins import EntariDrawingPool
from .providers import install_contract_providers
from .service import HtmlRenderService, _ServiceState

if TYPE_CHECKING:
    from collections.abc import Mapping

    from launart import Service

    from entari_plugin_htmlrender.adapters.resources.hosted import (
        HostedAssetHttpServer,
    )
    from entari_plugin_htmlrender.graphics.drawing_loader import DrawingSpec
    from entari_plugin_htmlrender.graphics.drawings import (
        DrawingRegistryFactory,
        DrawingSourceRegistry,
    )
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor
    from entari_plugin_htmlrender.runtime import RenderRuntime


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
    runtime: RenderRuntime | None = None
    sources: list[DrawingSourceRegistry] = []
    state = _ServiceState()

    async def close_sources() -> None:
        # A failed staged composition has no service to perform its cleanup.
        # Once built, use the current generation's runtime gate so admitted
        # drawings finish first. Closed generations are not retained here.
        if state.current is not None:
            await state.current._close(renew=False)
        elif runtime is not None:
            await runtime.aclose()
        else:
            for source in sources:
                await source.aclose()

    collect_disposes(close_sources)
    pool = keeping(
        "htmlrender.drawings",
        obj_factory=EntariDrawingPool,
        dispose=EntariDrawingPool.aclose,
    )

    def drawing_registry(
        definitions: Mapping[str, DrawingSpec], *, worker: WorkerExecutor
    ) -> DrawingSourceRegistry:
        source = pool.registry(definitions, worker=worker)
        sources.append(source)
        return source

    runtime = plan.build_runtime(drawing_registry_factory=drawing_registry)
    sources.clear()
    owner = get_plugin()
    # Subscriber provider records can survive atomic plugin reloads. Expose
    # this owner's state on its module so they resolve the current generation.
    vars(owner.module)["_htmlrender_service_state"] = state

    async def build_generation(
        drawing_registry_factory: DrawingRegistryFactory,
    ) -> tuple[RenderRuntime, HostedAssetHttpServer | None]:
        # The fresh plan is built only when the successor prepares.  In
        # particular, configured drawing modules are not imported while the
        # owner is disabled.
        nonlocal runtime
        source_start = len(sources)
        try:
            replacement_plan = build_runtime_plan(config)
            replacement_runtime = replacement_plan.build_runtime(
                drawing_registry_factory=drawing_registry_factory,
            )
        except BaseException as build_error:
            partial_sources = sources[source_start:]
            del sources[source_start:]
            cleanup_errors: list[BaseException] = []
            with anyio.CancelScope(shield=True):
                for source in reversed(partial_sources):
                    try:
                        await source.aclose()
                    except BaseException as cleanup_error:
                        cleanup_errors.append(cleanup_error)
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "HTMLRender replacement composition and rollback both failed.",
                    [build_error, *cleanup_errors],
                ) from build_error
            raise
        runtime = replacement_runtime
        sources.clear()
        return replacement_runtime, replacement_plan.hosted_asset_server

    def can_renew() -> bool:
        manager = it(Launart)
        return (
            plugin_service.plugins.get(owner.id) is owner
            and owner.available
            and not owner.is_available
            and manager.status.stage == "blocking"
            and not manager.status.exiting
        )

    service = HtmlRenderService(
        runtime,
        config,
        hosted_asset_server=plan.hosted_asset_server,
        runtime_factory=build_generation,
        drawing_registry_factory=drawing_registry,
        owner=owner,
        can_renew=can_renew,
        state=state,
    )
    install_contract_providers()
    add_service(cast("Service", service))
    return service


__all__ = ["register_plugin"]
