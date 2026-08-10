"""Render runtime aggregate: renderer, capabilities, and lifecycle."""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, final

import anyio

from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog
from entari_plugin_htmlrender.rendering.errors import (
    ProviderLifecycleError,
    RenderingError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from entari_plugin_htmlrender.preparation.service import HtmlPreparer
    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.ports import RuntimeLifecycle
    from entari_plugin_htmlrender.resources.service import ResourceService

    from .facades import RuntimeResources
    from .renderer import HtmlRenderer

from .extensions import RuntimeExtensions
from .facades import AdmittedHtmlPreparer, AdmittedResourceService


class _RuntimeState(Enum):
    NEW = auto()
    STARTED = auto()
    CLOSING = auto()
    CLOSED = auto()


@final
class RenderRuntime:
    """Host-neutral aggregate composed once for one rendering lifetime."""

    def __init__(
        self,
        *,
        renderer: HtmlRenderer,
        preparation: HtmlPreparer,
        resources: ResourceService,
        lifecycle: RuntimeLifecycle,
        operation_admission: OperationAdmissionGate,
        extensions: CapabilityCatalog | None = None,
    ) -> None:
        self._renderer = renderer
        self._operation_admission = operation_admission
        self._preparation = AdmittedHtmlPreparer(preparation, self._operation_admission)
        self._resources = AdmittedResourceService(resources, self._operation_admission)
        self._lifecycle = lifecycle
        catalog = extensions if extensions is not None else CapabilityCatalog()
        self._extensions = RuntimeExtensions(catalog)
        self._state = _RuntimeState.NEW
        self._lock = anyio.Lock()

    @property
    def renderer(self) -> HtmlRenderer:
        return self._renderer

    @property
    def preparation(self) -> HtmlPreparer:
        return self._preparation

    @property
    def resources(self) -> RuntimeResources:
        return self._resources

    @property
    def extensions(self) -> RuntimeExtensions:
        return self._extensions

    async def _run_lifecycle(
        self,
        operation: str,
        callback: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            await callback()
        except RenderingError:
            raise
        except Exception as error:
            raise ProviderLifecycleError(
                f"Render runtime lifecycle {operation} failed.",
                source=error,
            ) from error

    async def startup(self) -> None:
        """Start the provider runtime; idempotent and concurrency-safe."""
        async with self._lock:
            if self._state in {_RuntimeState.CLOSING, _RuntimeState.CLOSED}:
                raise ProviderLifecycleError(
                    "Render runtime is closing or closed; build a new composition "
                    "to render again."
                )
            if self._state is _RuntimeState.STARTED:
                return
            await self._run_lifecycle("startup", self._lifecycle.startup)
            self._state = _RuntimeState.STARTED

    async def probe(self) -> None:
        """Run the provider-defined minimal probe."""
        await self.startup()
        async with self._lock:
            if self._state is not _RuntimeState.STARTED:
                raise ProviderLifecycleError(
                    "Render runtime is closing or closed; build a new composition "
                    "to probe again."
                )
            await self._run_lifecycle("probe", self._lifecycle.probe)

    async def aclose(self) -> None:
        """Close the provider runtime; idempotent for multiple callers."""
        async with self._lock:
            if self._state is _RuntimeState.CLOSED:
                return
            # A failed teardown remains retryable, but startup is permanently
            # rejected once closing has begun.
            self._state = _RuntimeState.CLOSING
            await self._operation_admission.stop_accepting_and_drain()
            await self._run_lifecycle("aclose", self._lifecycle.aclose)
            self._state = _RuntimeState.CLOSED
