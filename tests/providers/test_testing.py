from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import anyio
import pytest

from entari_plugin_htmlrender.errors import RuntimeUnavailableError
from entari_plugin_htmlrender.providers import RenderProvider
from entari_plugin_htmlrender.providers.testing import (
    ProviderConformanceError,
    RuntimeFactory,
    run_provider_lifecycle_conformance,
    run_provider_startup_retry_conformance,
)
from entari_plugin_htmlrender.runtime import RenderRuntime
from tests.image_fixtures import rendered_image

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _runtime(mocker: MockerFixture) -> Any:
    runtime = mocker.create_autospec(RenderRuntime, instance=True)
    runtime.renderer.rasterize_html = mocker.AsyncMock(return_value=rendered_image())
    return runtime


def _provider(mocker: MockerFixture) -> RenderProvider[Any]:
    return cast(
        "RenderProvider[Any]",
        mocker.Mock(spec=RenderProvider),
    )


def _compose(runtime: object) -> RuntimeFactory:
    def compose(_provider: RenderProvider[Any]) -> RenderRuntime:
        return cast("RenderRuntime", runtime)

    return compose


async def test_lifecycle_conformance_success(mocker: MockerFixture) -> None:
    runtime = _runtime(mocker)
    runtime.startup.side_effect = [
        None,
        None,
        RuntimeUnavailableError("closed", operation="startup"),
    ]

    await run_provider_lifecycle_conformance(
        _provider(mocker),
        _compose(runtime),
    )

    assert runtime.startup.await_count == 3
    assert runtime.probe.await_count == 2
    runtime.renderer.rasterize_html.assert_awaited_once_with("<p>conformance</p>")
    assert runtime.aclose.await_count == 2


@pytest.mark.parametrize("stage", ("startup", "probe", "render", "artifact"))
async def test_lifecycle_conformance_closes_after_failure(
    mocker: MockerFixture,
    stage: str,
) -> None:
    runtime = _runtime(mocker)
    failure = RuntimeError("failure")
    if stage == "startup":
        runtime.startup.side_effect = failure
    elif stage == "probe":
        runtime.probe.side_effect = failure
    elif stage == "render":
        runtime.renderer.rasterize_html.side_effect = failure
    else:
        runtime.renderer.rasterize_html.return_value = object()

    with pytest.raises(BaseException) as captured:
        await run_provider_lifecycle_conformance(
            _provider(mocker),
            _compose(runtime),
        )

    runtime.aclose.assert_awaited_once_with()
    if stage == "artifact":
        assert type(captured.value) is ProviderConformanceError
        assert captured.value.args == (
            "render_html must return a typed RenderedImage artifact",
        )
    else:
        assert captured.value is failure


async def test_lifecycle_conformance_shields_cleanup_from_cancellation(
    mocker: MockerFixture,
) -> None:
    runtime = _runtime(mocker)
    render_started = anyio.Event()
    close_started = anyio.Event()
    close_release = anyio.Event()

    async def block_render(*args: object, **kwargs: object) -> None:
        del args, kwargs
        render_started.set()
        await anyio.sleep_forever()

    async def block_close() -> None:
        close_started.set()
        await close_release.wait()

    runtime.renderer.rasterize_html.side_effect = block_render
    runtime.aclose.side_effect = block_close
    provider = _provider(mocker)
    compose = _compose(runtime)

    async def run_conformance() -> None:
        await run_provider_lifecycle_conformance(provider, compose)

    async def cancel_during_render() -> None:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_conformance)
            await render_started.wait()
            task_group.cancel_scope.cancel()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(cancel_during_render)
        with anyio.fail_after(1):
            await close_started.wait()
        close_release.set()

    runtime.aclose.assert_awaited_once_with()


async def test_lifecycle_conformance_aggregates_original_and_cleanup_errors(
    mocker: MockerFixture,
) -> None:
    runtime = _runtime(mocker)
    render_error = RuntimeError("render")
    cleanup_error = RuntimeError("cleanup")
    runtime.renderer.rasterize_html.side_effect = render_error
    runtime.aclose.side_effect = cleanup_error

    with pytest.raises(BaseExceptionGroup) as captured:
        await run_provider_lifecycle_conformance(
            _provider(mocker),
            _compose(runtime),
        )

    assert captured.value.exceptions == (render_error, cleanup_error)
    assert captured.value.__cause__ is render_error
    runtime.aclose.assert_awaited_once_with()


@pytest.mark.parametrize("harness", ("lifecycle", "startup_retry"))
async def test_conformance_rejects_invalid_runtime_with_stable_error(
    mocker: MockerFixture,
    harness: str,
) -> None:
    provider = _provider(mocker)
    compose = _compose(object())
    fail_once = mocker.Mock()

    with pytest.raises(ProviderConformanceError) as captured:
        if harness == "lifecycle":
            await run_provider_lifecycle_conformance(provider, compose)
        else:
            await run_provider_startup_retry_conformance(
                provider,
                compose,
                fail_once=fail_once,
            )

    assert type(captured.value) is ProviderConformanceError
    assert captured.value.args == ("compose must return a RenderRuntime",)
    assert captured.value.__cause__ is None
    fail_once.assert_not_called()


async def test_startup_retry_conformance_success(
    mocker: MockerFixture,
) -> None:
    runtime = _runtime(mocker)
    runtime.startup.side_effect = [RuntimeError("transient"), None]
    fail_once = mocker.Mock()

    await run_provider_startup_retry_conformance(
        _provider(mocker),
        _compose(runtime),
        fail_once=fail_once,
    )

    fail_once.assert_called_once_with()
    assert runtime.startup.await_count == 2
    runtime.renderer.rasterize_html.assert_awaited_once_with("<p>ok</p>")
    runtime.aclose.assert_awaited_once_with()


async def test_startup_retry_conformance_closes_when_arming_check_fails(
    mocker: MockerFixture,
) -> None:
    runtime = _runtime(mocker)
    arm_error = RuntimeError("arm")
    fail_once = mocker.Mock(side_effect=arm_error)

    with pytest.raises(RuntimeError) as captured:
        await run_provider_startup_retry_conformance(
            _provider(mocker),
            _compose(runtime),
            fail_once=fail_once,
        )

    assert captured.value is arm_error
    runtime.startup.assert_not_awaited()
    runtime.aclose.assert_awaited_once_with()
