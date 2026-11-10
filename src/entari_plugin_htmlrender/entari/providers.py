"""Letoderea providers for the caller-facing HTMLRender contracts."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, cast

from arclet.entari.plugin import find_plugin, get_plugin
from arclet.entari.plugin.service import plugin_service
from arclet.letoderea import (
    Contexts,
    Param,
    Provider,
    ProviderFactory,
    global_providers,
)
from creart import it
from launart import Launart, Service

from entari_plugin_htmlrender.graphics import GraphicsRenderer
from entari_plugin_htmlrender.preparation.service import HtmlPreparer
from entari_plugin_htmlrender.rendering.contracts import (
    HtmlRenderer,
    TemplateRenderer,
)
from entari_plugin_htmlrender.resources import ResourceAccess

from .service import HtmlRenderService


class _ContractProvider(Provider[Any]):
    """Resolve one direct contract from the plugin-owned runtime service."""

    def __init__(self, contract: type[Any]) -> None:
        self.contract = contract
        self.origin = contract

    @staticmethod
    async def _wait_for_prepared(
        manager: Launart,
        lifecycle: Service,
        service_id: str,
    ) -> None:
        """Wake on preparation, or fail if the selected lifecycle stops."""
        task_group = getattr(manager, "task_group", None)
        trackers = getattr(task_group, "sideload_trackers", {})
        tasks = getattr(manager, "tasks", {})
        trigger = trackers.get(service_id) or tasks.get(service_id)
        prepared = asyncio.create_task(lifecycle.status.wait_for("prepared"))
        try:
            if trigger is None:
                await prepared
                return
            done, _ = await asyncio.wait(
                {prepared, trigger},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            prepared.cancel()
            with suppress(asyncio.CancelledError):
                await prepared

        if prepared in done or lifecycle.status.prepared:
            return
        try:
            trigger.result()
        except asyncio.CancelledError:
            raise RuntimeError(
                f"Entari HTMLRender service {service_id!r} stopped during preparation."
            ) from None
        except Exception as error:
            raise RuntimeError(
                f"Entari HTMLRender service {service_id!r} failed during preparation."
            ) from error
        raise RuntimeError(
            f"Entari HTMLRender service {service_id!r} exited before preparation."
        )

    async def _active_service(self) -> HtmlRenderService:
        manager = it(Launart)
        service_id = HtmlRenderService.id
        while True:
            try:
                component = manager.get_component(service_id)
            except ValueError:
                plugin = find_plugin("entari_plugin_htmlrender")
                if plugin is None:
                    raise RuntimeError("Entari HTMLRender is not loaded.") from None
                if not plugin.is_available:
                    raise RuntimeError("Entari HTMLRender is disabled.") from None
                await plugin_service.service_waiter.wait_for(service_id)
                continue

            lifecycle = component
            stage = lifecycle.status.stage
            if stage in {"prepared", "blocking"}:
                return cast("HtmlRenderService", component)
            if stage in {None, "waiting-for-prepare", "preparing"}:
                await self._wait_for_prepared(manager, lifecycle, service_id)
                continue

            tracker = None
            task_group = getattr(manager, "task_group", None)
            if task_group is not None:
                trackers = getattr(task_group, "sideload_trackers", {})
                tracker = trackers.get(service_id)
            if tracker is not None and not tracker.done():
                await asyncio.wait({tracker})
                continue
            raise RuntimeError(
                f"Entari HTMLRender service is not active (stage={stage!r})."
            )

    async def __call__(self, context: Contexts) -> Any:
        del context
        component = await self._active_service()

        if self.contract is HtmlRenderer:
            return component.renderer
        if self.contract is TemplateRenderer:
            return component.templates
        if self.contract is HtmlPreparer:
            return component.preparation
        if self.contract is ResourceAccess:
            return component.resources
        if self.contract is GraphicsRenderer:
            return component.graphics
        raise RuntimeError(f"Unsupported HTMLRender contract: {self.contract!r}")

    def __repr__(self) -> str:
        return f"HtmlRenderContractProvider(origin={self.contract!r})"


class HtmlRenderContractProviderFactory(ProviderFactory):
    """Expose HTMLRender's caller contracts through Entari's DI system."""

    contracts: tuple[type[Any], ...] = (
        HtmlRenderer,
        TemplateRenderer,
        HtmlPreparer,
        ResourceAccess,
        GraphicsRenderer,
    )

    def validate(self, param: Param) -> Provider[Any] | None:
        if not any(param.annotation is contract for contract in self.contracts):
            return None
        return _ContractProvider(param.annotation)


def install_contract_providers() -> None:
    """Register providers whose lifetime is owned by the current Entari plugin."""
    factory = HtmlRenderContractProviderFactory()
    global_providers.append(factory)
    plugin = get_plugin(1)

    def remove_factory() -> None:
        with suppress(ValueError):
            global_providers.remove(factory)

    plugin.collect(remove_factory)


__all__ = [
    "HtmlRenderContractProviderFactory",
    "install_contract_providers",
]
