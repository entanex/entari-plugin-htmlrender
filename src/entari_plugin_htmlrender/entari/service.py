"""Launart ownership for one Entari-scoped HTMLRender composition."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol, final

from exceptiongroup import BaseExceptionGroup
from launart import Launart
from launart.status import Phase  # noqa: TC002 -- public annotation contract

from entari_plugin_htmlrender._logging import logger
from entari_plugin_htmlrender.config import HtmlRenderConfig, RuntimeStartupPolicy
from entari_plugin_htmlrender.graphics import GraphicsRenderer  # noqa: TC001
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
    from contextlib import AbstractAsyncContextManager

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


@final
class HtmlRenderService(_ServiceBase):
    """Concrete Entari service exposing only caller-facing render contracts."""

    id = "htmlrender.runtime"

    def __init__(
        self,
        runtime: RenderRuntime,
        config: HtmlRenderConfig,
        *,
        hosted_asset_server: _HostedAssetServer | None = None,
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._config = config.model_copy(deep=True)
        self._hosted_asset_server = hosted_asset_server
        self._close_lock = asyncio.Lock()
        self._closed = False

    @property
    def required(self) -> set[str]:
        return set()

    @property
    def stages(self) -> set[Phase]:
        return {"preparing", "blocking", "cleanup"}

    @property
    def renderer(self) -> HtmlRenderer:
        return self._runtime.renderer

    @property
    def templates(self) -> TemplateRenderer:
        return self._runtime.templates

    @property
    def resources(self) -> ResourceAccess:
        return self._runtime.resources

    @property
    def graphics(self) -> GraphicsRenderer:
        return self._runtime.graphics

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._runtime.capabilities

    async def _prepare(self) -> None:
        try:
            if self._hosted_asset_server is not None:
                await self._hosted_asset_server.startup()
            if self._config.startup is not RuntimeStartupPolicy.OFF:
                await self._runtime.startup()
                if self._config.startup is RuntimeStartupPolicy.PROBE:
                    await self._runtime.probe()
        except BaseException as startup_error:
            try:
                await self._close()
            except BaseException as close_error:
                raise BaseExceptionGroup(
                    "HTMLRender startup failed and rollback also failed.",
                    [startup_error, close_error],
                ) from startup_error
            raise

    async def _close(self) -> None:
        """Drain runtime work before closing host transport; failures retry."""
        async with self._close_lock:
            if self._closed:
                return

            errors: list[BaseException] = []
            try:
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
                return
            if len(errors) == 1:
                raise errors[0]
            raise BaseExceptionGroup("HTMLRender service shutdown failed.", errors)

    async def launch(self, manager: Launart) -> None:
        """Participate in Entari startup, blocking, and hot-unload cleanup."""
        async with self.stage("preparing"):
            logger.info("Preparing the HTMLRender runtime")
            await self._prepare()
        async with self.stage("blocking"):
            await manager.status.wait_for_sigexit()
        async with self.stage("cleanup"):
            logger.info("Closing the HTMLRender runtime")
            await self._close()


__all__ = ["HtmlRenderService"]
