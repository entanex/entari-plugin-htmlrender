"""Host-neutral conformance harness for third-party engine providers.

The harness ships with the production package so provider authors can run the
same lifecycle checks from an installed wheel. It has no test-runner or host
dependency: callers supply a composition function and wrap the coroutines in
pytest, unittest, or another runner. Violations raise
:class:`ProviderConformanceError`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

from entari_plugin_htmlrender.providers.sdk import EngineProvider
from entari_plugin_htmlrender.rendering import (
    ProviderLifecycleError,
    RenderedImage,
    RenderHtmlRequest,
)
from entari_plugin_htmlrender.runtime import RenderRuntime

RuntimeFactory: TypeAlias = Callable[[EngineProvider[Any]], RenderRuntime]


class ProviderConformanceError(AssertionError):
    """A provider violated the documented lifecycle contract."""


def _require(*, condition: bool, message: str) -> None:
    if not condition:
        raise ProviderConformanceError(message)


async def run_provider_lifecycle_conformance(
    provider: EngineProvider[Any],
    compose: RuntimeFactory,
) -> None:
    """Exercise the fault-free lifecycle invariants of one provider.

    Covers: compose produces a runtime without performing I/O; startup,
    probe and aclose are each idempotent; a rendered artifact is typed; and a
    closed runtime rejects a fresh startup.
    """
    # Composition is I/O-free: obtaining the runtime must not start it.
    runtime = compose(provider)
    _require(
        condition=isinstance(runtime, RenderRuntime),
        message="compose must return a RenderRuntime",
    )

    # Idempotent startup.
    await runtime.startup()
    await runtime.startup()

    # Probe does not change ownership and can be repeated.
    await runtime.probe()
    await runtime.probe()

    artifact = await runtime.renderer.render_html(
        RenderHtmlRequest(html="<p>conformance</p>")
    )
    _require(
        condition=isinstance(artifact, RenderedImage),
        message="render_html must return a typed RenderedImage artifact",
    )
    _require(
        condition=bool(bytes(artifact)),
        message="the rendered artifact must carry bytes",
    )

    # Idempotent shutdown.
    await runtime.aclose()
    await runtime.aclose()

    # A closed runtime refuses to start again.
    try:
        await runtime.startup()
    except ProviderLifecycleError:
        return
    raise ProviderConformanceError(
        "a closed runtime must reject a fresh startup with ProviderLifecycleError"
    )


async def run_provider_startup_retry_conformance(
    provider: EngineProvider[Any],
    compose: RuntimeFactory,
    *,
    fail_once: Callable[[], None],
) -> None:
    """Assert startup is retryable after a single transient failure.

    ``fail_once`` is a callable the caller uses to arm a one-shot failure in
    the provider's runtime before the first startup; after the failed startup
    a second startup must succeed.
    """
    runtime = compose(provider)

    fail_once()
    try:
        await runtime.startup()
    except Exception:  # noqa: S110 -- provider-defined error type
        pass
    else:
        raise ProviderConformanceError(
            "the armed one-shot startup failure did not surface"
        )

    try:
        await runtime.startup()
        await runtime.renderer.render_html(RenderHtmlRequest(html="<p>ok</p>"))
    finally:
        await runtime.aclose()


__all__ = [
    "ProviderConformanceError",
    "RuntimeFactory",
    "run_provider_lifecycle_conformance",
    "run_provider_startup_retry_conformance",
]
