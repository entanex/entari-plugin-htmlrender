from __future__ import annotations

from contextlib import suppress
from importlib import import_module
from importlib.util import find_spec
import inspect
import threading
from typing import TYPE_CHECKING, final

from entari_plugin_htmlrender._logging import logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from types import ModuleType


@final
class OptionalModuleLoader:
    """Import one optional SDK module at most once and cache the outcome.

    Discovery and import are serialized; failures are cached so a broken
    optional integration is probed exactly once per process.
    """

    def __init__(self, module: str) -> None:
        self._module = module
        self._lock = threading.RLock()
        self._checked = False
        self._loaded: ModuleType | None = None

    def load(self, *, reason: str) -> ModuleType | None:
        with self._lock:
            if self._checked:
                return self._loaded
            self._checked = True
            self._loaded = self._bootstrap(reason)
            return self._loaded

    def _bootstrap(self, reason: str) -> ModuleType | None:
        try:
            installed = find_spec(self._module) is not None
        except Exception as error:
            logger.warning(
                "Cannot locate optional telemetry module %s (%s): %s.",
                self._module,
                reason,
                error,
            )
            return None
        if not installed:
            logger.debug(
                "Optional telemetry module %s is not installed; skipping %s.",
                self._module,
                reason,
            )
            return None

        try:
            module = import_module(self._module)
        except Exception as error:
            logger.warning(
                "Optional telemetry module %s import failed (%s): %s.",
                self._module,
                reason,
                error,
            )
            return None

        logger.debug(
            "Optional telemetry module %s is ready (%s).",
            self._module,
            reason,
        )
        return module


def normalize_backend(backend: str | None) -> str:
    """Normalize a provider or graphics backend into a metric label string."""
    if backend is None:
        return "unknown"
    return str(backend)


def metric_params(fn: Callable[..., object]) -> set[str]:
    """Return the parameter names of ``fn``.

    The result is deliberately not cached: caching would add process-level
    mutable state to the observability adapter, and ``id`` reuse after object
    destruction could produce false hits.
    """
    try:
        return set(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return set()


def call_metric(
    fn: Callable[..., object],
    name: str,
    value: float | int,
    *,
    unit: str | None,
    tags: Mapping[str, str],
) -> None:
    """Invoke a metric recorder while adapting to its parameter naming.

    Supports the ``value``/``amount`` conventions for the metric value and
    the ``tags``/``attributes`` conventions for labels.
    """
    params = metric_params(fn)
    kwargs: dict[str, object] = {}
    if "unit" in params and unit is not None:
        kwargs["unit"] = unit
    if "tags" in params:
        kwargs["tags"] = dict(tags)
    if "attributes" in params:
        kwargs["attributes"] = dict(tags)

    if "value" in params:
        kwargs["value"] = value
        fn(name, **kwargs)
        return
    if "amount" in params:
        kwargs["amount"] = value
        fn(name, **kwargs)
        return

    fn(name, value, **kwargs)


def set_span_attribute(span: object, key: str, value: object) -> None:
    """Set one attribute on a tracing span.

    Prefers ``set_attribute`` and falls back to ``set_data`` so both
    OpenTelemetry-style and Sentry-style span APIs are supported.
    """
    try:
        set_attribute = getattr(span, "set_attribute", None)
    except Exception:
        set_attribute = None
    if callable(set_attribute):
        with suppress(Exception):
            set_attribute(key, value)
            return

    try:
        set_data = getattr(span, "set_data", None)
    except Exception:
        set_data = None
    if callable(set_data):
        with suppress(Exception):
            set_data(key, value)


def set_span_status(span: object, status: str) -> None:
    """Set the status string (for example ``ok`` or ``error``) on a span."""
    try:
        set_status = getattr(span, "set_status", None)
    except Exception:
        return
    if not callable(set_status):
        return
    with suppress(Exception):
        set_status(status)


def get_trace_id(span: object) -> str | None:
    """Extract the trace id string from a tracing span, if available."""
    try:
        trace_id = getattr(span, "trace_id", None)
    except Exception:
        return None
    if isinstance(trace_id, str):
        return trace_id or None

    try:
        to_string = getattr(trace_id, "to_string", None)
    except Exception:
        return None
    if not callable(to_string):
        return None
    with suppress(Exception):
        trace_value = to_string()
        if isinstance(trace_value, str):
            return trace_value
        return str(trace_value)
    return None
