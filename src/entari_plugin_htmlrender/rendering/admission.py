"""Runtime-wide admission control for rendering operations."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, final

import anyio

from entari_plugin_htmlrender.errors import RuntimeUnavailableError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@final
class OperationAdmissionGate:
    """Admit complete use-case operations and drain them before shutdown.

    The gate is deliberately part of the neutral rendering boundary.  Every
    runtime-owned facade can share it without making provider adapters depend
    on the runtime package.
    """

    def __init__(self) -> None:
        self._lock = anyio.Lock()
        self._state = "open"
        self._active_operations = 0
        self._drained = anyio.Event()
        self._drained.set()

    def ensure_accepting(self, operation: str | None = None) -> None:
        """Reject synchronous facade operations after shutdown begins."""
        if self._state != "open":
            raise RuntimeUnavailableError(self._state, operation=operation)

    @asynccontextmanager
    async def operation(
        self,
        operation: str | None = None,
    ) -> AsyncIterator[None]:
        """Admit one operation for its complete preparation/execution span."""
        async with self._lock:
            self.ensure_accepting(operation)
            if self._active_operations == 0:
                self._drained = anyio.Event()
            self._active_operations += 1

        try:
            yield
        finally:
            # Cancellation is sticky in AnyIO.  Shield the accounting update so
            # a cancelled render cannot leave shutdown waiting forever.
            with anyio.CancelScope(shield=True):
                async with self._lock:
                    self._active_operations -= 1
                    if self._active_operations == 0:
                        self._drained.set()

    async def stop_accepting_and_drain(self) -> None:
        """Permanently reject new operations, then wait for admitted work."""
        # The state transition must survive cancellation.  Waiting for existing
        # operations remains cancellable so RenderRuntime.aclose() can be retried.
        with anyio.CancelScope(shield=True):
            async with self._lock:
                if self._state == "open":
                    self._state = "closing"
        # No new operation can be admitted anymore, so the drained event can
        # no longer be replaced and reading it outside the lock is stable.
        await self._drained.wait()

    async def mark_closed(self) -> None:
        """Record that lifecycle teardown completed after the drain."""
        with anyio.CancelScope(shield=True):
            async with self._lock:
                self._state = "closed"


__all__ = ["OperationAdmissionGate"]
