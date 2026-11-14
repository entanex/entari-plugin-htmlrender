"""Launart ownership for Entari-scoped HTMLRender compositions."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol, cast, final

from launart import Launart, Service
from launart.status import Phase  # noqa: TC002 -- public annotation contract

from entari_plugin_htmlrender._logging import logger
from entari_plugin_htmlrender.config import HtmlRenderConfig, RuntimeStartupPolicy
from entari_plugin_htmlrender.errors import RuntimeUnavailableError
from entari_plugin_htmlrender.graphics import GraphicsRenderer  # noqa: TC001
from entari_plugin_htmlrender.graphics.drawings import DrawingRenderer  # noqa: TC001
from entari_plugin_htmlrender.preparation.service import HtmlPreparer  # noqa: TC001
from entari_plugin_htmlrender.rendering.contracts import (  # noqa: TC001
    HtmlRenderer,
    TemplateRenderer,
)
from entari_plugin_htmlrender.resources import ResourceAccess  # noqa: TC001
from entari_plugin_htmlrender.runtime import (  # noqa: TC001
    RenderRuntime,
    RuntimeCapabilities,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from arclet.entari.plugin.model import Plugin

    from entari_plugin_htmlrender.graphics.drawings import (
        DrawingRegistryFactory,
    )

    class _ServiceBase:
        """Typed view of the untyped Launart base used only for analysis."""

        id: str

        def __init__(self) -> None: ...

        def stage(self, stage: Phase) -> AbstractAsyncContextManager[None]: ...

else:
    from launart import Service as _ServiceBase


class _HostedAssetServer(Protocol):
    async def startup(self) -> None: ...

    async def aclose(self) -> None: ...


class RuntimeFactory(Protocol):
    async def __call__(
        self,
        drawing_registry_factory: DrawingRegistryFactory,
    ) -> tuple[RenderRuntime, _HostedAssetServer | None]: ...


class _ServiceState:
    """Plugin-owned failure and cleanup owner across service generations."""

    def __init__(self) -> None:
        self.current: HtmlRenderService | None = None
        self.error: BaseException | None = None

    def ensure_available(self) -> None:
        if self.error is not None:
            raise RuntimeUnavailableError(
                "failed", operation="service facade"
            ) from self.error

    def fail(self, error: BaseException) -> None:
        self.error = (
            error
            if self.error is None
            else BaseExceptionGroup(
                "HTMLRender managed lifecycle failed.", [self.error, error]
            )
        )


@final
class HtmlRenderService(_ServiceBase):
    """Concrete Entari service exposing only caller-facing render contracts."""

    id = "htmlrender.runtime"

    def __init__(
        self,
        runtime: RenderRuntime | None,
        config: HtmlRenderConfig,
        *,
        hosted_asset_server: _HostedAssetServer | None = None,
        runtime_factory: RuntimeFactory | None = None,
        drawing_registry_factory: DrawingRegistryFactory | None = None,
        owner: Plugin | None = None,
        can_renew: Callable[[], bool] | None = None,
        state: _ServiceState | None = None,
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._config = config.model_copy(deep=True)
        self._hosted_asset_server = hosted_asset_server
        self._runtime_factory = runtime_factory
        self._drawing_registry_factory = drawing_registry_factory
        self._owner = owner
        self._can_renew = can_renew
        self._state = state or _ServiceState()
        self._state.current = self
        self._close_lock = asyncio.Lock()
        self._prepared = False
        self._closed = False

    @property
    def required(self) -> set[str]:
        return set()

    @property
    def stages(self) -> set[Phase]:
        return {"preparing", "blocking", "cleanup"}

    def _require_runtime(self) -> RenderRuntime:
        self._state.ensure_available()
        if self._runtime is None:
            raise RuntimeUnavailableError("preparing", operation="service facade")
        return self._runtime

    @property
    def renderer(self) -> HtmlRenderer:
        return self._require_runtime().renderer

    @property
    def templates(self) -> TemplateRenderer:
        return self._require_runtime().templates

    @property
    def preparation(self) -> HtmlPreparer:
        return self._require_runtime().preparation

    @property
    def resources(self) -> ResourceAccess:
        return self._require_runtime().resources

    @property
    def graphics(self) -> GraphicsRenderer:
        return self._require_runtime().graphics

    @property
    def drawings(self) -> DrawingRenderer:
        return self._require_runtime().drawings

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._require_runtime().capabilities

    async def _build_runtime(self) -> None:
        factory = self._runtime_factory
        drawing_registry_factory = self._drawing_registry_factory
        if factory is None or drawing_registry_factory is None:
            raise RuntimeUnavailableError("preparing", operation="runtime.build")
        self._runtime, self._hosted_asset_server = await factory(
            drawing_registry_factory
        )

    def _renew_after_disable(self) -> None:
        """Queue one lazy successor while its disabled owner still exists."""
        owner = self._owner
        can_renew = self._can_renew
        runtime_factory = self._runtime_factory
        if (
            owner is None
            or can_renew is None
            or runtime_factory is None
            or self._state.error is not None
            or not can_renew()
            or owner.is_available
        ):
            return
        successor = HtmlRenderService(
            None,
            self._config,
            runtime_factory=runtime_factory,
            drawing_registry_factory=self._drawing_registry_factory,
            owner=owner,
            can_renew=can_renew,
            state=self._state,
        )
        owner.service(cast("Service", successor))

    async def _prepare(self) -> None:
        try:
            if self._runtime is None:
                await self._build_runtime()
            runtime = self._require_runtime()
            if self._hosted_asset_server is not None:
                await self._hosted_asset_server.startup()
            if self._config.startup is not RuntimeStartupPolicy.OFF:
                await runtime.startup()
                if self._config.startup is RuntimeStartupPolicy.PROBE:
                    await runtime.probe()
            self._prepared = True
        except BaseException as startup_error:
            try:
                await self._close(renew=False)
            except BaseException as close_error:
                raise BaseExceptionGroup(
                    "HTMLRender startup failed and rollback also failed.",
                    [startup_error, close_error],
                ) from startup_error
            raise

    async def _close(self, *, renew: bool = True) -> None:
        """Drain runtime work before closing host transport; failures retry."""
        async with self._close_lock:
            if self._closed:
                return

            errors: list[BaseException] = []
            try:
                if self._runtime is not None:
                    await self._runtime.aclose()
            except asyncio.CancelledError:
                # A cancelled drain is retryable. The server must remain alive
                # until every admitted operation has released its resources.
                raise
            except BaseException as error:
                errors.append(error)

            if self._hosted_asset_server is not None:
                try:
                    await self._hosted_asset_server.aclose()
                except BaseException as error:
                    errors.append(error)

            if not errors:
                self._closed = True
                if renew and self._prepared:
                    self._renew_after_disable()
                return
            if len(errors) == 1:
                raise errors[0]
            raise BaseExceptionGroup("HTMLRender service shutdown failed.", errors)

    async def launch(self, manager: Launart) -> None:
        """Participate in Entari startup, blocking, and hot-unload cleanup."""
        async with self.stage("preparing"):
            logger.info("Preparing the HTMLRender runtime")
            try:
                await self._prepare()
            except BaseException as error:
                self._state.fail(error)
                logger.exception(
                    "HTMLRender preparation failed; reload the plugin to recover."
                )

        async with self.stage("blocking"):
            if self._state.error is None:
                await manager.status.wait_for_sigexit()

        async with self.stage("cleanup"):
            logger.info("Closing the HTMLRender runtime")
            try:
                await self._close(renew=self._state.error is None)
            except BaseException as error:
                self._state.fail(error)
                logger.exception(
                    "HTMLRender cleanup failed; reload the plugin to recover."
                )
        # Both stage contexts and the launch task must finish normally so
        # Entari's waiters wake and Launart removes the sideload component.
        # The recorded fault keeps facades and DI unavailable until reload;
        # plugin disposal can still retry _close() on this generation.


__all__ = ["HtmlRenderService"]
