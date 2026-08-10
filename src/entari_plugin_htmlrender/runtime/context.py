"""Task-local resolution boundary for host-owned render runtimes."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Protocol, TypeAlias

from entari_plugin_htmlrender.rendering.errors import RuntimeNotBound

from .runtime import RenderRuntime

if TYPE_CHECKING:
    from collections.abc import Iterator


class RuntimeResolver(Protocol):
    """Resolve a host-owned runtime without exposing the host container.

    Resolution is deliberately synchronous and local. Implementations must not
    perform startup, I/O, or composition; the host owns those lifecycle steps.
    """

    def resolve_runtime(self) -> RenderRuntime: ...


RuntimeSource: TypeAlias = RenderRuntime | RuntimeResolver

_runtime_source: ContextVar[RuntimeSource | None] = ContextVar(
    "htmlrender_runtime_source",
    default=None,
)


def resolve_runtime(source: RuntimeSource | None = None) -> RenderRuntime:
    """Resolve an explicit or task-local render runtime.

    An explicit source always wins. If omitted, the source bound by
    :func:`runtime_context` is used. No process-global runtime or factory is
    consulted.
    """

    candidate = source if source is not None else _runtime_source.get()
    if candidate is None:
        raise RuntimeNotBound(
            "No RenderRuntime is bound to the current context; pass `runtime=` "
            "explicitly or enter runtime_context(...)."
        )
    runtime = (
        candidate
        if isinstance(candidate, RenderRuntime)
        else candidate.resolve_runtime()
    )
    if not isinstance(runtime, RenderRuntime):
        raise TypeError("RuntimeResolver.resolve_runtime() must return RenderRuntime.")
    return runtime


@contextmanager
def runtime_context(source: RuntimeSource) -> Iterator[RenderRuntime]:
    """Bind a runtime source to the current task and child-task context."""

    runtime = resolve_runtime(source)
    token = _runtime_source.set(runtime)
    try:
        yield runtime
    finally:
        _runtime_source.reset(token)


__all__ = [
    "RuntimeResolver",
    "RuntimeSource",
    "resolve_runtime",
    "runtime_context",
]
