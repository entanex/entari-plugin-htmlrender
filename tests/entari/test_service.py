from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from exceptiongroup import BaseExceptionGroup
from launart import Launart, Service
import pytest

from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.entari import HtmlRenderService

if TYPE_CHECKING:
    from launart.status import Phase

    from entari_plugin_htmlrender.runtime import RenderRuntime


@dataclass
class _Runtime:
    events: list[str] = field(default_factory=list)
    startup_errors: list[BaseException] = field(default_factory=list)
    probe_errors: list[BaseException] = field(default_factory=list)
    close_errors: list[BaseException] = field(default_factory=list)
    close_entered: asyncio.Event | None = None
    close_release: asyncio.Event | None = None
    renderer: object = field(default_factory=object)
    templates: object = field(default_factory=object)
    resources: object = field(default_factory=object)
    graphics: object = field(default_factory=object)
    capabilities: object = field(default_factory=object)

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
        if self.close_entered is not None:
            self.close_entered.set()
        if self.close_release is not None:
            await self.close_release.wait()
        if self.close_errors:
            raise self.close_errors.pop(0)


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
    runtime: _Runtime | None = None,
    server: _HostedAssetServer | None = None,
) -> tuple[HtmlRenderService, _Runtime]:
    owned_runtime = runtime or _Runtime()
    config = HtmlRenderConfig.model_validate(
        {
            "provider": "fake" if startup != "off" else None,
            "startup": startup,
        }
    )
    return (
        HtmlRenderService(
            cast("RenderRuntime", owned_runtime),
            config,
            hosted_asset_server=server,
        ),
        owned_runtime,
    )


def _launart_service(service: HtmlRenderService) -> Service:
    """View the runtime subclass through the framework-owned lifecycle type."""
    return cast("Service", service)


async def _launch_and_stop(service: HtmlRenderService) -> None:
    manager = Launart()
    lifecycle = _launart_service(service)
    manager.add_component(lifecycle)
    launch = asyncio.create_task(manager.launch())
    await asyncio.wait_for(lifecycle.status.wait_for("prepared"), timeout=5)
    manager.status.exiting = True
    await asyncio.wait_for(launch, timeout=5)


def test_service_exposes_only_caller_facing_services() -> None:
    service, runtime = _service("off")

    assert service.renderer is runtime.renderer
    assert service.templates is runtime.templates
    assert service.resources is runtime.resources
    assert service.graphics is runtime.graphics
    assert service.capabilities is runtime.capabilities
    assert not hasattr(service, "resolve_runtime")
    assert not hasattr(service, "settings")
    assert not hasattr(service, "aclose")


async def test_launart_owns_warmup_and_probe_lifecycle() -> None:
    warmup, warmup_runtime = _service("warmup")
    probe, probe_runtime = _service("probe")

    await _launch_and_stop(warmup)
    await _launch_and_stop(probe)

    assert warmup_runtime.events == ["runtime.startup", "runtime.aclose"]
    assert probe_runtime.events == [
        "runtime.startup",
        "runtime.probe",
        "runtime.aclose",
    ]
    assert _launart_service(warmup).status.stage == "finished"
    assert _launart_service(probe).status.stage == "finished"


async def test_off_mode_skips_startup_but_closes_owned_runtime() -> None:
    service, runtime = _service("off")

    await _launch_and_stop(service)

    assert runtime.events == ["runtime.aclose"]


async def test_startup_failure_rolls_back_runtime_and_filehost() -> None:
    events: list[str] = []
    runtime = _Runtime(
        events=events,
        startup_errors=[RuntimeError("startup failed")],
    )
    server = _HostedAssetServer(events)
    service, _ = _service("warmup", runtime, server)

    with pytest.raises(RuntimeError, match="startup failed"):
        await service._prepare()

    assert events == [
        "server.startup",
        "runtime.startup",
        "runtime.aclose",
        "server.aclose",
    ]


async def test_startup_and_rollback_failures_are_aggregated() -> None:
    runtime = _Runtime(
        startup_errors=[RuntimeError("startup failed")],
        close_errors=[RuntimeError("close failed")],
    )
    service, _ = _service("warmup", runtime)

    with pytest.raises(BaseExceptionGroup) as captured:
        await service._prepare()

    assert [str(error) for error in captured.value.exceptions] == [
        "startup failed",
        "close failed",
    ]


async def test_filehost_startup_failure_still_closes_both_owners() -> None:
    events: list[str] = []
    runtime = _Runtime(events=events)
    server = _HostedAssetServer(
        events,
        startup_errors=[RuntimeError("bind failed")],
    )
    service, _ = _service("warmup", runtime, server)

    with pytest.raises(RuntimeError, match="bind failed"):
        await service._prepare()

    assert events == [
        "server.startup",
        "runtime.aclose",
        "server.aclose",
    ]


async def test_close_is_concurrency_safe_and_idempotent() -> None:
    service, runtime = _service("off")

    await asyncio.gather(service._close(), service._close(), service._close())
    await service._close()

    assert runtime.events == ["runtime.aclose"]


async def test_failed_close_is_retried() -> None:
    runtime = _Runtime(close_errors=[RuntimeError("close failed")])
    service, _ = _service("off", runtime)

    with pytest.raises(RuntimeError, match="close failed"):
        await service._close()
    await service._close()

    assert runtime.events == ["runtime.aclose", "runtime.aclose"]


async def test_close_aggregates_runtime_and_filehost_failures() -> None:
    events: list[str] = []
    runtime = _Runtime(
        events=events,
        close_errors=[RuntimeError("runtime close failed")],
    )
    server = _HostedAssetServer(
        events,
        close_errors=[RuntimeError("server close failed")],
    )
    service, _ = _service("off", runtime, server)

    with pytest.raises(BaseExceptionGroup) as captured:
        await service._close()

    assert [str(error) for error in captured.value.exceptions] == [
        "runtime close failed",
        "server close failed",
    ]
    assert events == ["runtime.aclose", "server.aclose"]


async def test_cancelled_runtime_drain_keeps_filehost_open_for_retry() -> None:
    events: list[str] = []
    entered = asyncio.Event()
    release = asyncio.Event()
    runtime = _Runtime(
        events=events,
        close_entered=entered,
        close_release=release,
    )
    server = _HostedAssetServer(events)
    service, _ = _service("off", runtime, server)

    close_task = asyncio.create_task(service._close())
    await asyncio.wait_for(entered.wait(), timeout=5)
    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task

    assert events == ["runtime.aclose"]

    release.set()
    await service._close()
    assert events == [
        "runtime.aclose",
        "runtime.aclose",
        "server.aclose",
    ]


async def test_hot_unload_runs_cleanup_before_service_removal() -> None:
    manager = Launart()
    sentinel = _SentinelService()
    manager.add_component(sentinel)
    launch = asyncio.create_task(manager.launch())
    await asyncio.wait_for(sentinel.status.wait_for("blocking"), timeout=5)

    service, runtime = _service("warmup")
    lifecycle = _launart_service(service)
    manager.add_component(lifecycle)
    await asyncio.wait_for(lifecycle.status.wait_for("blocking"), timeout=5)

    manager.remove_component(lifecycle)
    await asyncio.wait_for(lifecycle.status.wait_for("finished"), timeout=5)

    assert runtime.events == ["runtime.startup", "runtime.aclose"]

    manager.status.exiting = True
    await asyncio.wait_for(launch, timeout=5)
