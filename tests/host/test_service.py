from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from exceptiongroup import BaseExceptionGroup
from launart import Launart, Service
import pytest

from entari_plugin_htmlrender.host._service import HtmlRenderService
from entari_plugin_htmlrender.host.composition import compose_runtime
from entari_plugin_htmlrender.host.config import RenderSettings
from entari_plugin_htmlrender.providers.sdk import (
    EngineBindings,
    ProviderAvailability,
)
from entari_plugin_htmlrender.rendering import (
    ProviderLifecycleError,
    RenderedImage,
    RenderHtmlRequest,
)
from entari_plugin_htmlrender.resources.config import ResourceStrategy
from tests.image_fixtures import rendered_image

if TYPE_CHECKING:
    from collections.abc import Mapping

    from launart.status import Phase

    from entari_plugin_htmlrender.adapters.resources import HostedAssetHttpServer
    from entari_plugin_htmlrender.preparation.models import PreparedHtml, RasterOptions
    from entari_plugin_htmlrender.providers.sdk import ProviderDependencies
    from entari_plugin_htmlrender.rendering.ports import PreparedHtmlExecutor
    from entari_plugin_htmlrender.rendering.requests import ResourcePolicy
    from entari_plugin_htmlrender.runtime import RenderRuntime


@dataclass
class _Lifecycle:
    events: list[str] = field(default_factory=list)
    startup_errors: list[BaseException] = field(default_factory=list)
    probe_errors: list[BaseException] = field(default_factory=list)
    close_errors: list[BaseException] = field(default_factory=list)

    async def startup(self) -> None:
        self.events.append("runtime.startup")
        if self.startup_errors:
            raise self.startup_errors.pop(0)

    async def probe(self) -> None:
        self.events.append("runtime.probe")
        if self.probe_errors:
            raise self.probe_errors.pop(0)

    async def aclose(self) -> None:
        self.events.append("runtime.aclose")
        if self.close_errors:
            raise self.close_errors.pop(0)


class _Provider:
    id = "fake"

    def __init__(
        self,
        lifecycle: _Lifecycle,
        executor: PreparedHtmlExecutor | None = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._executor = executor

    def parse_settings(self, raw: Mapping[str, object]) -> object:
        return dict(raw)

    def availability(self, settings: object) -> ProviderAvailability:
        del settings
        return ProviderAvailability(available=True)

    def resource_strategy(self, settings: object) -> ResourceStrategy:
        del settings
        return ResourceStrategy()

    def compose(
        self,
        settings: object,
        dependencies: ProviderDependencies,
    ) -> EngineBindings:
        del settings, dependencies
        return EngineBindings(
            lifecycle=self._lifecycle,
            prepared_html_executor=self._executor,
        )


@dataclass
class _BlockingExecutor:
    events: list[str]
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def execute(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        resource_policy: ResourcePolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage:
        del prepared, options, resource_policy, timeout_seconds
        self.events.append("render.enter")
        self.entered.set()
        await self.release.wait()
        self.events.append("render.exit")
        return rendered_image()


@dataclass
class _HostedAssetServer:
    events: list[str]
    startup_errors: list[BaseException] = field(default_factory=list)
    close_errors: list[BaseException] = field(default_factory=list)

    async def startup(self) -> None:
        self.events.append("server.startup")
        if self.startup_errors:
            raise self.startup_errors.pop(0)

    async def aclose(self) -> None:
        self.events.append("server.aclose")
        if self.close_errors:
            raise self.close_errors.pop(0)


class _SentinelService(Service):
    id = "test.sentinel"

    @property
    def required(self) -> set[str]:
        return set()

    @property
    def stages(self) -> set[Phase]:
        return {"preparing", "blocking", "cleanup"}

    async def launch(self, manager: Launart) -> None:
        async with self.stage("preparing"):
            pass
        async with self.stage("blocking"):
            await manager.status.wait_for_sigexit()
        async with self.stage("cleanup"):
            pass


def _service(
    startup: str,
    lifecycle: _Lifecycle | None = None,
    executor: PreparedHtmlExecutor | None = None,
) -> tuple[HtmlRenderService, RenderRuntime, _Lifecycle]:
    owned_lifecycle = lifecycle or _Lifecycle()
    settings = RenderSettings.model_validate({"provider": "fake", "startup": startup})
    composition = compose_runtime(
        settings,
        explicit_providers=[_Provider(owned_lifecycle, executor)],
    )
    runtime = composition.build_runtime()
    return HtmlRenderService(runtime, settings), runtime, owned_lifecycle


async def _launch_and_stop(service: HtmlRenderService) -> None:
    manager = Launart()
    manager.add_component(service)
    launch = asyncio.create_task(manager.launch())
    await asyncio.wait_for(service.status.wait_for("prepared"), timeout=5)
    manager.status.exiting = True
    await asyncio.wait_for(launch, timeout=5)


async def test_warmup_lifecycle_is_owned_by_launart_service() -> None:
    service, runtime, lifecycle = _service("warmup")

    await _launch_and_stop(service)

    assert service.resolve_runtime() is runtime
    assert lifecycle.events == ["runtime.startup", "runtime.aclose"]
    assert service.status.stage == "finished"


async def test_probe_mode_starts_probes_and_closes_in_order() -> None:
    service, _, lifecycle = _service("probe")

    await _launch_and_stop(service)

    assert lifecycle.events == [
        "runtime.startup",
        "runtime.probe",
        "runtime.aclose",
    ]


async def test_off_mode_skips_startup_but_still_closes_owned_runtime() -> None:
    service, _, lifecycle = _service("off")

    await _launch_and_stop(service)

    assert lifecycle.events == ["runtime.aclose"]


async def test_startup_failure_closes_runtime_before_launart_aborts() -> None:
    lifecycle = _Lifecycle(startup_errors=[RuntimeError("startup failed")])
    service, _, _ = _service("warmup", lifecycle)
    manager = Launart()
    manager.add_component(service)

    await asyncio.wait_for(manager.launch(), timeout=5)

    assert lifecycle.events == ["runtime.startup", "runtime.aclose"]


async def test_startup_and_cleanup_failures_are_aggregated() -> None:
    lifecycle = _Lifecycle(
        startup_errors=[RuntimeError("startup failed")],
        close_errors=[RuntimeError("close failed")],
    )
    service, _, _ = _service("warmup", lifecycle)

    with pytest.raises(BaseExceptionGroup) as captured:
        await service._prepare_runtime()

    assert len(captured.value.exceptions) == 2
    await service.aclose()


async def test_close_is_concurrency_safe_and_idempotent() -> None:
    service, _, lifecycle = _service("off")

    await asyncio.gather(service.aclose(), service.aclose(), service.aclose())
    await service.aclose()

    assert lifecycle.events == ["runtime.aclose"]


async def test_failed_close_can_be_retried() -> None:
    lifecycle = _Lifecycle(close_errors=[RuntimeError("close failed")])
    service, _, _ = _service("off", lifecycle)

    with pytest.raises(ProviderLifecycleError, match="aclose"):
        await service.aclose()
    await service.aclose()

    assert lifecycle.events == ["runtime.aclose", "runtime.aclose"]


async def test_filehost_server_surrounds_runtime_lifecycle() -> None:
    events: list[str] = []
    lifecycle = _Lifecycle(events=events)
    service, runtime, _ = _service("warmup", lifecycle)
    server = _HostedAssetServer(events)
    service = HtmlRenderService(
        runtime,
        service.settings,
        hosted_asset_server=cast("HostedAssetHttpServer", server),
    )

    await _launch_and_stop(service)

    assert events == [
        "server.startup",
        "runtime.startup",
        "runtime.aclose",
        "server.aclose",
    ]


async def test_filehost_server_is_closed_when_its_startup_fails() -> None:
    events: list[str] = []
    lifecycle = _Lifecycle(events=events)
    service, runtime, _ = _service("warmup", lifecycle)
    server = _HostedAssetServer(
        events,
        startup_errors=[RuntimeError("bind failed")],
    )
    service = HtmlRenderService(
        runtime,
        service.settings,
        hosted_asset_server=cast("HostedAssetHttpServer", server),
    )
    manager = Launart()
    manager.add_component(service)

    await asyncio.wait_for(manager.launch(), timeout=5)

    assert events == [
        "server.startup",
        "runtime.aclose",
        "server.aclose",
    ]


async def test_shutdown_aggregates_runtime_and_server_failures() -> None:
    events: list[str] = []
    lifecycle = _Lifecycle(
        events=events,
        close_errors=[RuntimeError("runtime close failed")],
    )
    service, runtime, _ = _service("off", lifecycle)
    server = _HostedAssetServer(
        events,
        close_errors=[RuntimeError("server close failed")],
    )
    service = HtmlRenderService(
        runtime,
        service.settings,
        hosted_asset_server=cast("HostedAssetHttpServer", server),
    )

    with pytest.raises(BaseExceptionGroup) as captured:
        await service.aclose()

    assert len(captured.value.exceptions) == 2
    assert events == ["runtime.aclose", "server.aclose"]
    await service.aclose()


async def test_cancelled_runtime_drain_keeps_filehost_open_for_retry() -> None:
    events: list[str] = []
    lifecycle = _Lifecycle(events=events)
    executor = _BlockingExecutor(events)
    service, runtime, _ = _service("off", lifecycle, executor)
    server = _HostedAssetServer(events)
    service = HtmlRenderService(
        runtime,
        service.settings,
        hosted_asset_server=cast("HostedAssetHttpServer", server),
    )

    render_task = asyncio.create_task(
        runtime.renderer.render_html(RenderHtmlRequest(html="<p>in flight</p>"))
    )
    await asyncio.wait_for(executor.entered.wait(), timeout=5)

    close_task = asyncio.create_task(service.aclose())

    async def wait_for_runtime_drain() -> None:
        while True:
            try:
                runtime.resources.should_resolve()
            except ProviderLifecycleError:
                return
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_runtime_drain(), timeout=5)
    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task

    assert events == ["render.enter"]

    executor.release.set()
    await asyncio.wait_for(render_task, timeout=5)
    await service.aclose()

    assert events == [
        "render.enter",
        "render.exit",
        "runtime.aclose",
        "server.aclose",
    ]


async def test_hot_unload_runs_cleanup_before_service_is_removed() -> None:
    manager = Launart()
    sentinel = _SentinelService()
    manager.add_component(sentinel)
    launch = asyncio.create_task(manager.launch())
    await asyncio.wait_for(sentinel.status.wait_for("blocking"), timeout=5)

    service, _, lifecycle = _service("warmup")
    manager.add_component(service)
    await asyncio.wait_for(service.status.wait_for("blocking"), timeout=5)

    manager.remove_component(service)
    await asyncio.wait_for(service.status.wait_for("finished"), timeout=5)

    assert lifecycle.events == ["runtime.startup", "runtime.aclose"]

    manager.status.exiting = True
    await asyncio.wait_for(launch, timeout=5)
