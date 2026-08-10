from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from entari_plugin_htmlrender.rendering import RuntimeNotBound
from entari_plugin_htmlrender.runtime import (
    RenderRuntime,
    RuntimeResolver,
    resolve_runtime,
    runtime_context,
)


def _runtime() -> RenderRuntime:
    return object.__new__(RenderRuntime)


@dataclass(frozen=True)
class _Resolver:
    runtime: RenderRuntime

    def resolve_runtime(self) -> RenderRuntime:
        return self.runtime


def test_explicit_runtime_and_resolver_are_equivalent() -> None:
    runtime = _runtime()

    assert resolve_runtime(runtime) is runtime
    assert resolve_runtime(_Resolver(runtime)) is runtime


def test_runtime_context_is_nested_and_restores_outer_binding() -> None:
    outer = _runtime()
    inner = _runtime()

    with runtime_context(outer):
        assert resolve_runtime() is outer
        with runtime_context(_Resolver(inner)):
            assert resolve_runtime() is inner
        assert resolve_runtime() is outer

    with pytest.raises(RuntimeNotBound):
        resolve_runtime()


def test_explicit_runtime_takes_precedence_over_bound_context() -> None:
    bound = _runtime()
    explicit = _runtime()

    with runtime_context(bound):
        assert resolve_runtime(explicit) is explicit


def test_invalid_resolver_result_fails_loudly() -> None:
    invalid = _Resolver(cast("RenderRuntime", object()))

    with pytest.raises(TypeError, match="must return RenderRuntime"):
        resolve_runtime(cast("RuntimeResolver", invalid))
