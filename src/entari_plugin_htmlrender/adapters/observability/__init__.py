from __future__ import annotations

from contextlib import AbstractContextManager, asynccontextmanager, contextmanager
import sys
from time import perf_counter
from typing import TYPE_CHECKING

from entari_plugin_htmlrender._logging import logger
from entari_plugin_htmlrender.errors import RenderingError

from .common import get_trace_id, normalize_backend, set_span_attribute, set_span_status
from .prometheus import (
    record_cache_metrics as record_prometheus_cache_metrics,
)
from .prometheus import (
    record_filehost_cache_metrics as record_prometheus_filehost_cache_metrics,
)
from .prometheus import record_metrics as record_prometheus_metrics
from .sentry import (
    record_cache_metrics as record_sentry_cache_metrics,
)
from .sentry import (
    record_filehost_cache_metrics as record_sentry_filehost_cache_metrics,
)
from .sentry import record_metrics as record_sentry_metrics
from .sentry import start_trace

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Generator, Iterator, Mapping

    from entari_plugin_htmlrender.providers.sdk import EngineId


class TelemetryCacheObserver:
    """Instance-configured cache observer over selected exporters."""

    def __init__(self, *, sentry: bool, prometheus: bool) -> None:
        self._sentry = sentry
        self._prometheus = prometheus

    def record(
        self,
        cache: str,
        events: Mapping[str, int],
        entries: int,
        resident_bytes: int | None = None,
    ) -> None:
        record_cache_metrics(
            cache,
            events,
            entries,
            resident_bytes,
            sentry=self._sentry,
            prometheus=self._prometheus,
        )


@contextmanager
def _entered_trace(
    trace_context: object | None,
) -> Generator[object | None, None, None]:
    """Enter and finish a provider context without exposing provider failures."""
    if trace_context is None:
        yield None
        return

    try:
        enter = getattr(trace_context, "__enter__", None)
        exit_context = getattr(trace_context, "__exit__", None)
    except Exception as error:
        logger.warning(
            "Cannot inspect trace provider context: %s.",
            error,
        )
        yield None
        return
    if not callable(enter) or not callable(exit_context):
        logger.warning("Trace provider returned an invalid context manager.")
        yield None
        return

    try:
        span = enter()
    except Exception as error:
        logger.warning(
            "Trace provider enter failed: %s.",
            error,
        )
        yield None
        return

    try:
        yield span
    except BaseException:
        exc_type, exc, traceback = sys.exc_info()
        try:
            exit_context(exc_type, exc, traceback)
        except Exception as error:
            logger.warning(
                "Trace provider exit failed: %s.",
                error,
            )
        raise
    else:
        try:
            exit_context(None, None, None)
        except Exception as error:
            logger.warning(
                "Trace provider exit failed: %s.",
                error,
            )


def _record_metrics_safely(
    provider: str,
    recorder: Callable[..., object],
    *args: object,
) -> None:
    """Run one exporter without allowing observability to affect rendering."""
    if not callable(recorder):
        return
    try:
        recorder(*args)
    except Exception as error:
        logger.warning(
            "%s metric export failed: %s.",
            provider,
            error,
        )


def record_filehost_cache_metrics(
    event: str,
    value: int,
    active_mappings: int,
    active_leases: int,
    physical_cleanup_capable: int,
    *,
    sentry: bool,
    prometheus: bool,
) -> None:
    """Export one filehost cache event without affecting resource delivery."""

    args = (
        event,
        value,
        active_mappings,
        active_leases,
        physical_cleanup_capable,
    )
    if sentry:
        _record_metrics_safely(
            "Sentry",
            record_sentry_filehost_cache_metrics,
            *args,
        )
    if prometheus:
        _record_metrics_safely(
            "Prometheus",
            record_prometheus_filehost_cache_metrics,
            *args,
        )


def record_cache_metrics(
    cache: str,
    events: Mapping[str, int],
    entries: int,
    resident_bytes: int | None = None,
    *,
    sentry: bool,
    prometheus: bool,
) -> None:
    """Export low-cardinality cache event deltas and current capacity."""

    args = (cache, events, entries, resident_bytes)
    if sentry:
        _record_metrics_safely("Sentry", record_sentry_cache_metrics, *args)
    if prometheus:
        _record_metrics_safely("Prometheus", record_prometheus_cache_metrics, *args)


def _record_error(span: object, error: BaseException) -> None:
    """Attach bounded failure metadata without exporting raw native objects."""
    set_span_attribute(span, "error.type", type(error).__name__)
    if not isinstance(error, RenderingError):
        return
    set_span_attribute(span, "error.message", error.message)
    set_span_attribute(span, "error.message_truncated", error.message_truncated)
    set_span_attribute(
        span,
        "error.cause_types",
        ",".join(cause.exception_type for cause in error.causes),
    )
    set_span_attribute(span, "error.causes_truncated", error.causes_truncated)


@contextmanager
def _operation_context(
    op: str,
    *,
    backend: EngineId | None = None,
    name: str | None = None,
    attrs: Mapping[str, str] | None = None,
    sentry: bool,
    prometheus: bool,
) -> Iterator[None]:
    """Span creation, timing, and metric fan-out shared by every entry point."""
    backend_name = normalize_backend(backend)
    all_attrs = {"render.backend": backend_name}
    if attrs:
        all_attrs.update(attrs)

    trace_context = None
    if sentry:
        try:
            trace_context = start_trace(op, name or op, all_attrs)
        except Exception as error:
            logger.warning(
                "Trace provider initialization failed: %s.",
                error,
            )
    if trace_context is None:
        logger.debug(
            "Console telemetry fallback enabled op=%s backend=%s.",
            op,
            backend_name,
        )
    start_time = perf_counter()
    status = "ok"
    trace_id: str | None = None

    duration = 0.0
    try:
        with _entered_trace(trace_context) as span:
            try:
                yield
            except BaseException as error:
                status = "error"
                if span is not None:
                    _record_error(span, error)
                    set_span_status(span, status)
                raise
            finally:
                duration = perf_counter() - start_time
                if span is not None:
                    for key, value in all_attrs.items():
                        set_span_attribute(span, key, value)
                    set_span_attribute(span, "render.status", status)
                    set_span_attribute(span, "render.duration_seconds", duration)
                    trace_id = get_trace_id(span)
                    set_span_status(span, status)
                else:
                    logger.debug(
                        "Render perf op=%s backend=%s status=%s duration=%.6fs.",
                        op,
                        backend_name,
                        status,
                        duration,
                    )
    finally:
        if sentry:
            _record_metrics_safely(
                "Sentry",
                record_sentry_metrics,
                op,
                backend_name,
                status,
                duration,
            )
        if prometheus:
            _record_metrics_safely(
                "Prometheus",
                record_prometheus_metrics,
                op,
                backend_name,
                status,
                duration,
                trace_id,
            )


@asynccontextmanager
async def track_render(
    op: str,
    *,
    backend: EngineId | None = None,
    name: str | None = None,
    attrs: Mapping[str, str] | None = None,
    sentry: bool = False,
    prometheus: bool = False,
) -> AsyncIterator[None]:
    """Track one render operation across the explicitly selected exporters.

    Records duration and status around the operation and reports only to the
    Sentry/Prometheus exporters the caller opted into; without Sentry the
    span data falls back to console debug logging.  Exceptions from the
    wrapped operation are re-raised with the span marked as ``error``.
    """
    with _operation_context(
        op,
        backend=backend,
        name=name,
        attrs=attrs,
        sentry=sentry,
        prometheus=prometheus,
    ):
        yield


class TelemetryOperationObserver:
    """Instance-configured operation observer over selected exporters."""

    def __init__(self, *, sentry: bool, prometheus: bool) -> None:
        self._sentry = sentry
        self._prometheus = prometheus

    def observe(
        self,
        operation: str,
        attributes: Mapping[str, str],
    ) -> AbstractContextManager[None]:
        extra = dict(attributes)
        backend = extra.pop("render.backend", None)
        return _operation_context(
            operation,
            backend=backend,
            name=operation,
            attrs=extra,
            sentry=self._sentry,
            prometheus=self._prometheus,
        )
