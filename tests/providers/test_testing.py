from __future__ import annotations

from dataclasses import dataclass, field, replace
import importlib.util
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any, cast

import anyio
import pytest

from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.errors import (
    ProviderExecutionError,
    ProviderLifecycleError,
)
from entari_plugin_htmlrender.providers import (
    ProviderAvailability,
    ProviderBinding,
    ProviderDependencies,
    ProviderId,
    RenderProvider,
    ResourceStrategy,
)
from entari_plugin_htmlrender.providers.testing import (
    ProviderConformanceError,
    RuntimeFactory,
    run_provider_lifecycle_conformance,
    run_provider_startup_retry_conformance,
)
from entari_plugin_htmlrender.runtime import RenderRuntime, RuntimeState

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pytest_mock import MockerFixture

    from entari_plugin_htmlrender.preparation import PreparedHtml, RasterOptions
    from entari_plugin_htmlrender.rendering import RenderedImage, RenderOperation
    from entari_plugin_htmlrender.rendering.ports import (
        PreparedHtmlExecutor,
        RuntimeLifecycle,
    )
    from entari_plugin_htmlrender.resources.config import (
        ResourceMaterializationPolicy,
    )


_EXAMPLE_MODULE = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "echo-provider"
    / "src"
    / "htmlrender_echo_provider"
    / "__init__.py"
)


@dataclass(frozen=True, slots=True)
class _UntypedArtifact:
    data: bytes = b"not-a-rendered-image"
    width: int = 1
    height: int = 1


@dataclass(slots=True)
class _FaultPlan:
    startup_errors: list[Exception] = field(default_factory=list)
    probe_error: Exception | None = None
    render_error: Exception | None = None
    artifact: object | None = None
    close_error: Exception | None = None
    render_started: anyio.Event | None = None
    render_release: anyio.Event | None = None
    close_started: anyio.Event | None = None
    close_release: anyio.Event | None = None
    close_finished: anyio.Event | None = None
    close_calls: int = 0


class _FaultingLifecycle:
    def __init__(
        self,
        delegate: RuntimeLifecycle,
        faults: _FaultPlan,
    ) -> None:
        self._delegate = delegate
        self._faults = faults

    async def startup(self) -> None:
        if self._faults.startup_errors:
            raise self._faults.startup_errors.pop(0)
        await self._delegate.startup()

    async def probe(self) -> None:
        await self._delegate.probe()
        if self._faults.probe_error is not None:
            raise self._faults.probe_error

    async def aclose(self) -> None:
        await self._delegate.aclose()
        self._faults.close_calls += 1
        if self._faults.close_started is not None:
            self._faults.close_started.set()
        if self._faults.close_release is not None:
            await self._faults.close_release.wait()
        if self._faults.close_error is not None:
            raise self._faults.close_error
        if self._faults.close_finished is not None:
            self._faults.close_finished.set()


class _FaultingExecutor:
    def __init__(
        self,
        delegate: PreparedHtmlExecutor,
        faults: _FaultPlan,
    ) -> None:
        self._delegate = delegate
        self._faults = faults

    async def execute(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        operation: RenderOperation,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> RenderedImage:
        if self._faults.render_started is not None:
            self._faults.render_started.set()
        if self._faults.render_release is not None:
            await self._faults.render_release.wait()
        if self._faults.render_error is not None:
            raise self._faults.render_error
        if self._faults.artifact is not None:
            return cast("RenderedImage", self._faults.artifact)
        return await self._delegate.execute(
            prepared,
            options,
            operation=operation,
            materialization_policy=materialization_policy,
        )


class _FaultingProvider:
    def __init__(
        self,
        delegate: RenderProvider[Any],
        faults: _FaultPlan,
    ) -> None:
        self._delegate = delegate
        self._faults = faults

    @property
    def id(self) -> ProviderId:
        return self._delegate.id

    def parse_config(self, raw: Mapping[str, object]) -> Any:
        return self._delegate.parse_config(raw)

    def check_availability(self, config: Any) -> ProviderAvailability:
        return self._delegate.check_availability(config)

    def resource_strategy(self, config: Any) -> ResourceStrategy:
        return self._delegate.resource_strategy(config)

    def compose(
        self,
        config: Any,
        dependencies: ProviderDependencies,
    ) -> ProviderBinding:
        binding = self._delegate.compose(config, dependencies)
        executor = binding.prepared_html_executor
        if executor is None:
            raise AssertionError("the Echo provider must compose an executor")
        return replace(
            binding,
            lifecycle=_FaultingLifecycle(binding.lifecycle, self._faults),
            prepared_html_executor=_FaultingExecutor(executor, self._faults),
        )


def _load_echo_provider() -> RenderProvider[Any]:
    spec = importlib.util.spec_from_file_location(
        "htmlrender_echo_provider",
        _EXAMPLE_MODULE,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        provider = module.PROVIDER
    finally:
        sys.modules.pop(spec.name, None)
    assert isinstance(provider, RenderProvider)
    return provider


def _faulting_composition(
    faults: _FaultPlan,
) -> tuple[RenderProvider[Any], RuntimeFactory, list[RenderRuntime]]:
    provider = _FaultingProvider(_load_echo_provider(), faults)
    settings = HtmlRenderConfig.model_validate({"provider": "echo"})
    runtimes: list[RenderRuntime] = []

    def compose(selected: RenderProvider[Any]) -> RenderRuntime:
        runtime = build_runtime_plan(
            settings,
            provider_override=selected,
        ).build_runtime()
        runtimes.append(runtime)
        return runtime

    return provider, compose, runtimes


def _root_cause(error: BaseException) -> BaseException:
    while error.__cause__ is not None:
        error = error.__cause__
    return error


@pytest.mark.parametrize(
    ("stage", "expected_error"),
    (
        ("startup", ProviderLifecycleError),
        ("probe", ProviderLifecycleError),
        ("render", ProviderExecutionError),
        ("artifact", ProviderConformanceError),
    ),
)
async def test_lifecycle_conformance_closes_after_any_check_failure(
    stage: str,
    expected_error: type[BaseException],
) -> None:
    faults = _FaultPlan()
    if stage == "startup":
        faults.startup_errors.append(RuntimeError("startup root"))
    elif stage == "probe":
        faults.probe_error = RuntimeError("probe root")
    elif stage == "render":
        faults.render_error = RuntimeError("render root")
    else:
        faults.artifact = _UntypedArtifact()
    provider, compose, runtimes = _faulting_composition(faults)

    with pytest.raises(expected_error):
        await run_provider_lifecycle_conformance(provider, compose)

    assert len(runtimes) == 1
    assert runtimes[0].state is RuntimeState.CLOSED
    assert faults.close_calls == 1


async def test_lifecycle_conformance_keeps_idempotent_close_on_success(
    mocker: MockerFixture,
) -> None:
    faults = _FaultPlan()
    provider = _FaultingProvider(_load_echo_provider(), faults)
    settings = HtmlRenderConfig.model_validate({"provider": "echo"})
    runtimes: list[tuple[RenderRuntime, Any]] = []

    def compose(selected: RenderProvider[Any]) -> RenderRuntime:
        runtime = build_runtime_plan(
            settings,
            provider_override=selected,
        ).build_runtime()
        runtimes.append((runtime, mocker.spy(runtime, "aclose")))
        return runtime

    await run_provider_lifecycle_conformance(provider, compose)

    assert len(runtimes) == 1
    runtime, aclose = runtimes[0]
    assert runtime.state is RuntimeState.CLOSED
    assert aclose.await_count == 2


@pytest.mark.parametrize("harness", ("lifecycle", "startup_retry"))
async def test_conformance_rejects_invalid_runtime_before_cleanup(
    harness: str,
) -> None:
    invalid_runtime = cast("RenderRuntime", object())
    compose_calls = 0
    fail_once_calls = 0

    def compose(selected: RenderProvider[Any]) -> RenderRuntime:
        nonlocal compose_calls
        del selected
        compose_calls += 1
        return invalid_runtime

    def fail_once() -> None:
        nonlocal fail_once_calls
        fail_once_calls += 1

    with pytest.raises(ProviderConformanceError) as captured:
        if harness == "lifecycle":
            await run_provider_lifecycle_conformance(
                _load_echo_provider(),
                compose,
            )
        else:
            await run_provider_startup_retry_conformance(
                _load_echo_provider(),
                compose,
                fail_once=fail_once,
            )

    assert type(captured.value) is ProviderConformanceError
    assert captured.value.args == ("compose must return a RenderRuntime",)
    assert captured.value.__cause__ is None
    assert compose_calls == 1
    assert fail_once_calls == 0


async def test_lifecycle_conformance_aggregates_primary_and_cleanup_errors() -> None:
    render_error = RuntimeError("render root")
    close_error = RuntimeError("cleanup root")
    faults = _FaultPlan(render_error=render_error, close_error=close_error)
    provider, compose, runtimes = _faulting_composition(faults)

    with pytest.raises(BaseExceptionGroup) as captured:
        await run_provider_lifecycle_conformance(provider, compose)

    assert len(captured.value.exceptions) == 2
    assert [_root_cause(error) for error in captured.value.exceptions] == [
        render_error,
        close_error,
    ]
    assert len(runtimes) == 1
    assert runtimes[0].state is RuntimeState.CLOSING
    assert faults.close_calls == 1


async def test_lifecycle_conformance_shields_cleanup_from_cancellation() -> None:
    faults = _FaultPlan(
        render_started=anyio.Event(),
        render_release=anyio.Event(),
        close_started=anyio.Event(),
        close_release=anyio.Event(),
        close_finished=anyio.Event(),
    )
    provider, compose, runtimes = _faulting_composition(faults)

    async def run_conformance() -> None:
        await run_provider_lifecycle_conformance(provider, compose)

    async def cancel_during_render() -> None:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_conformance)
            assert faults.render_started is not None
            await faults.render_started.wait()
            task_group.cancel_scope.cancel()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(cancel_during_render)
        assert faults.close_started is not None
        with anyio.fail_after(1):
            await faults.close_started.wait()
        assert faults.close_release is not None
        faults.close_release.set()

    assert len(runtimes) == 1
    assert runtimes[0].state is RuntimeState.CLOSED
    assert faults.close_calls == 1
    assert faults.close_finished is not None
    assert faults.close_finished.is_set()


async def test_startup_retry_closes_when_fail_once_raises() -> None:
    faults = _FaultPlan()
    provider, compose, runtimes = _faulting_composition(faults)
    arm_error = RuntimeError("fail_once root")

    def fail_once() -> None:
        raise arm_error

    with pytest.raises(RuntimeError) as captured:
        await run_provider_startup_retry_conformance(
            provider,
            compose,
            fail_once=fail_once,
        )

    assert captured.value is arm_error
    assert len(runtimes) == 1
    assert runtimes[0].state is RuntimeState.CLOSED
    assert faults.close_calls == 1


async def test_startup_retry_closes_when_first_startup_unexpectedly_succeeds() -> None:
    faults = _FaultPlan()
    provider, compose, runtimes = _faulting_composition(faults)

    with pytest.raises(
        ProviderConformanceError,
        match="armed one-shot startup failure did not surface",
    ):
        await run_provider_startup_retry_conformance(
            provider,
            compose,
            fail_once=lambda: None,
        )

    assert len(runtimes) == 1
    assert runtimes[0].state is RuntimeState.CLOSED
    assert faults.close_calls == 1


async def test_startup_retry_succeeds_after_transient_startup_failure() -> None:
    faults = _FaultPlan()
    provider, compose, runtimes = _faulting_composition(faults)

    await run_provider_startup_retry_conformance(
        provider,
        compose,
        fail_once=lambda: faults.startup_errors.append(
            RuntimeError("transient startup")
        ),
    )

    assert len(runtimes) == 1
    assert runtimes[0].state is RuntimeState.CLOSED
    assert faults.close_calls == 1


async def test_startup_retry_aggregates_render_and_cleanup_errors() -> None:
    render_error = RuntimeError("retry render root")
    close_error = RuntimeError("retry cleanup root")
    faults = _FaultPlan(render_error=render_error, close_error=close_error)
    provider, compose, runtimes = _faulting_composition(faults)

    with pytest.raises(BaseExceptionGroup) as captured:
        await run_provider_startup_retry_conformance(
            provider,
            compose,
            fail_once=lambda: faults.startup_errors.append(
                RuntimeError("transient startup")
            ),
        )

    assert [_root_cause(error) for error in captured.value.exceptions] == [
        render_error,
        close_error,
    ]
    assert len(runtimes) == 1
    assert runtimes[0].state is RuntimeState.CLOSING
    assert faults.close_calls == 1
