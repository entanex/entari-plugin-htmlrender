"""Lifecycle-owned aggregate assembled by the composition layer."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, final

import anyio

from entari_plugin_htmlrender.errors import (
    HtmlRenderError,
    ProviderLifecycleError,
    RuntimeUnavailableError,
)
from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from entari_plugin_htmlrender.graphics.ports import GraphicsRenderer
    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.contracts import (
        HtmlRenderer,
        TemplateRenderer,
    )
    from entari_plugin_htmlrender.rendering.ports import RuntimeLifecycle
    from entari_plugin_htmlrender.resources.ports import ResourceAccess

from .capabilities import RuntimeCapabilities
from .facades import _AdmittedResourceAccess


class RuntimeState(str, Enum):
    """Observable lifecycle state of one composed render runtime."""

    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


@final
class RenderRuntime:
    """Advanced composition aggregate owned by one host lifetime.

    Ordinary business code receives one of ``renderer``, ``templates``,
    ``resources``, ``graphics``, or ``capabilities`` instead of this lifecycle
    controller.
    """

    def __init__(
        self,
        *,
        renderer: HtmlRenderer,
        templates: TemplateRenderer,
        resources: ResourceAccess,
        graphics: GraphicsRenderer,
        lifecycle: RuntimeLifecycle,
        operation_admission: OperationAdmissionGate,
        capabilities: CapabilityCatalog | None = None,
        provider_id: str | None = None,
    ) -> None:
        self._renderer = renderer
        self._templates = templates
        self._resources = _AdmittedResourceAccess(resources, operation_admission)
        self._graphics = graphics
        self._capabilities = RuntimeCapabilities(
            capabilities if capabilities is not None else CapabilityCatalog()
        )
        self._lifecycle = lifecycle
        self._operation_admission = operation_admission
        self._provider_id = provider_id
        self._state = RuntimeState.OPEN
        self._started = False
        self._lock = anyio.Lock()

    @property
    def renderer(self) -> HtmlRenderer:
        return self._renderer

    @property
    def templates(self) -> TemplateRenderer:
        return self._templates

    @property
    def resources(self) -> ResourceAccess:
        return self._resources

    @property
    def graphics(self) -> GraphicsRenderer:
        return self._graphics

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._capabilities

    @property
    def state(self) -> RuntimeState:
        """Return the current lifecycle state without performing I/O."""
        return self._state

    async def _run_lifecycle(
        self,
        operation: str,
        callback: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            await callback()
        except HtmlRenderError:
            raise
        except Exception as error:
            raise ProviderLifecycleError(
                f"Render provider lifecycle {operation} failed.",
                provider_id=self._provider_id,
                operation=operation,
                retryable=True,
                source=error,
            ) from error

    async def startup(self) -> None:
        """Start the selected provider; idempotent and concurrency-safe."""
        async with self._lock:
            if self._state in {RuntimeState.CLOSING, RuntimeState.CLOSED}:
                raise RuntimeUnavailableError(
                    self._state.value,
                    operation="startup",
                )
            if self._started:
                return
            await self._run_lifecycle("startup", self._lifecycle.startup)
            self._started = True

    async def probe(self) -> None:
        """Run the provider-defined minimal readiness probe."""
        await self.startup()
        async with self._lock:
            if self._state is not RuntimeState.OPEN:
                raise RuntimeUnavailableError(
                    self._state.value,
                    operation="probe",
                )
            await self._run_lifecycle("probe", self._lifecycle.probe)

    async def aclose(self) -> None:
        """Drain caller operations and close the composition; failures retry."""
        async with self._lock:
            if self._state is RuntimeState.CLOSED:
                return
            self._state = RuntimeState.CLOSING
            await self._operation_admission.stop_accepting_and_drain()
            await self._run_lifecycle("aclose", self._lifecycle.aclose)
            await self._operation_admission.mark_closed()
            self._state = RuntimeState.CLOSED


__all__ = ["RenderRuntime", "RuntimeState"]
