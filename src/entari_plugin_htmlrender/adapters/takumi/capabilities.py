"""Typed Takumi capability resolved at the API/composition boundary."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, final

from entari_plugin_htmlrender.adapters.takumi.advanced import TakumiAPIAdapter
from entari_plugin_htmlrender.adapters.takumi.api import (
    TakumiSessionAdapter,
    _translate_managed_error,
)
from entari_plugin_htmlrender.adapters.takumi.runtime import require_runtime_state
from entari_plugin_htmlrender.capabilities.takumi import _TakumiLeaseGuard
from entari_plugin_htmlrender.rendering.observers import observe_operation

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from takumi_py import Renderer

    from entari_plugin_htmlrender.adapters._lease import ExecutionLeaseProvider
    from entari_plugin_htmlrender.adapters.takumi.runtime import TakumiRuntimeState
    from entari_plugin_htmlrender.capabilities.takumi import (
        TakumiAPI,
        TakumiSession,
    )
    from entari_plugin_htmlrender.rendering.ports import (
        OperationAdmission,
        OperationObserver,
    )

_OBSERVATION_ATTRIBUTES = {
    "render.backend": "takumi",
    "render.access": "native",
}
_LEASE_NATIVE_RENDERER_OPERATION = "takumi.lease_native_renderer"
_LEASE_SESSION_OPERATION = "takumi.lease_session"
_LEASE_API_OPERATION = "takumi.lease_api"


@final
class TakumiCapabilityAdapter:
    """Lease the small session, advanced API, or native Renderer.

    ``lease_session()`` yields the managed stable session.
    ``lease_api()`` yields the complete managed Takumi API.
    ``lease_native_renderer()`` yields the upstream object for explicitly
    unmanaged native operations.
    """

    def __init__(
        self,
        leases: ExecutionLeaseProvider[TakumiRuntimeState],
        observer: OperationObserver,
        *,
        operation_admission: OperationAdmission,
    ) -> None:
        self._leases = leases
        self._observer = observer
        self._operation_admission = operation_admission

    @asynccontextmanager
    async def lease_session(self) -> AsyncIterator[TakumiSession]:
        async with (
            self._operation_admission.operation(_LEASE_SESSION_OPERATION),
            self._leases.lease() as state,
        ):
            with _translate_managed_error(_LEASE_SESSION_OPERATION):
                runtime = require_runtime_state(state)
                lease_guard = _TakumiLeaseGuard(runtime)
                session = TakumiSessionAdapter(
                    runtime,
                    self._observer,
                    lease_guard,
                )
            try:
                yield session
            finally:
                lease_guard.invalidate()

    @asynccontextmanager
    async def lease_api(self) -> AsyncIterator[TakumiAPI]:
        async with (
            self._operation_admission.operation(_LEASE_API_OPERATION),
            self._leases.lease() as state,
        ):
            with _translate_managed_error(_LEASE_API_OPERATION):
                runtime = require_runtime_state(state)
                lease_guard = _TakumiLeaseGuard(runtime)
                api = TakumiAPIAdapter(
                    runtime,
                    self._observer,
                    lease_guard,
                )
            try:
                yield api
            finally:
                lease_guard.invalidate()

    @asynccontextmanager
    async def lease_native_renderer(self) -> AsyncIterator[Renderer]:
        """Lease the provider-owned native renderer without proxying it."""
        async with self._operation_admission.operation(
            _LEASE_NATIVE_RENDERER_OPERATION
        ):
            with observe_operation(
                self._observer,
                "takumi.native.renderer",
                _OBSERVATION_ATTRIBUTES,
            ):
                async with self._leases.lease() as state:
                    runtime = require_runtime_state(state)
                    renderer = runtime.renderer
                    if renderer is None:
                        raise RuntimeError("Takumi runtime does not expose a Renderer.")
                    yield renderer


__all__ = ["TakumiCapabilityAdapter"]
