"""Entari registration and Launart ownership of one render runtime."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, final

from exceptiongroup import BaseExceptionGroup
from launart import Launart, Service

from entari_plugin_htmlrender._logging import logger

from .config import RenderSettings, RenderStartupMode

if TYPE_CHECKING:
    from launart.status import Phase

    from entari_plugin_htmlrender.adapters.resources import HostedAssetHttpServer
    from entari_plugin_htmlrender.runtime import RenderRuntime


@final
class HtmlRenderService(Service):
    """Own one composed runtime for exactly one Entari plugin lifetime."""

    id = "htmlrender.runtime"

    def __init__(
        self,
        runtime: RenderRuntime,
        settings: RenderSettings,
        *,
        hosted_asset_server: HostedAssetHttpServer | None = None,
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._settings = settings.model_copy(deep=True)
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
    def settings(self) -> RenderSettings:
        """Return a detached view of the configuration owned by this service."""
        return self._settings.model_copy(deep=True)

    def resolve_runtime(self) -> RenderRuntime:
        """Return the already-composed runtime without starting or rebuilding it."""
        return self._runtime

    async def _prepare_runtime(self) -> None:
        settings = self._settings
        try:
            if self._hosted_asset_server is not None:
                await self._hosted_asset_server.startup()
            if (
                settings.provider is not None
                and settings.startup is not RenderStartupMode.OFF
            ):
                await self._runtime.startup()
                if settings.startup is RenderStartupMode.PROBE:
                    await self._runtime.probe()
        except BaseException as startup_error:
            try:
                await self.aclose()
            except BaseException as close_error:
                raise BaseExceptionGroup(
                    "Render runtime startup failed and cleanup also failed.",
                    [startup_error, close_error],
                ) from startup_error
            raise

    async def aclose(self) -> None:
        """Close the owned runtime once; a failed close remains retryable."""
        async with self._close_lock:
            if self._closed:
                return
            errors: list[BaseException] = []
            try:
                await self._runtime.aclose()
            except asyncio.CancelledError:
                # The runtime may still be draining admitted operations.  Its
                # close transition is retryable, but the filehost must remain
                # available until that drain has completed successfully.
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
        """Drive startup, readiness waiting, and teardown through Launart."""
        async with self.stage("preparing"):
            logger.info("Preparing the HTMLRender runtime")
            await self._prepare_runtime()
        async with self.stage("blocking"):
            await manager.status.wait_for_sigexit()
        async with self.stage("cleanup"):
            logger.info("Closing the HTMLRender runtime")
            await self.aclose()


__all__ = ["HtmlRenderService"]
