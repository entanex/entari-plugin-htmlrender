from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

import anyio
import anyio.lowlevel
from exceptiongroup import ExceptionGroup
import pytest

from entari_plugin_htmlrender.errors import (
    ProviderLifecycleError,
    RuntimeUnavailableError,
)
from entari_plugin_htmlrender.rendering import (
    CapabilityCatalog,
    CapabilityKey,
    OperationAdmissionGate,
)
from entari_plugin_htmlrender.resources import (
    FileResourceRef,
    ResourceContent,
)
from entari_plugin_htmlrender.runtime import RenderRuntime, RuntimeState

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from entari_plugin_htmlrender.graphics import GraphicsRenderer
    from entari_plugin_htmlrender.rendering.contracts import (
        HtmlRenderer,
        TemplateRenderer,
    )
    from entari_plugin_htmlrender.resources import (
        InlineResource,
        PublishedResource,
        ResourceRef,
    )
    from entari_plugin_htmlrender.resources.ports import ResourceAccess


_RENDERER = cast("HtmlRenderer", object())
_TEMPLATES = cast("TemplateRenderer", object())
_GRAPHICS = cast("GraphicsRenderer", object())


@dataclass
class _FakeLifecycle:
    startup_calls: int = 0
    probe_calls: int = 0
    aclose_calls: int = 0
    startup_failures: list[Exception] = field(default_factory=list)
    aclose_failures: list[Exception] = field(default_factory=list)

    async def startup(self) -> None:
        self.startup_calls += 1
        await anyio.lowlevel.checkpoint()
        if self.startup_failures:
            raise self.startup_failures.pop(0)

    async def probe(self) -> None:
        self.probe_calls += 1

    async def aclose(self) -> None:
        self.aclose_calls += 1
        if self.aclose_failures:
            raise self.aclose_failures.pop(0)


@dataclass
class _FakeResources:
    fetch_calls: int = 0
    started: anyio.Event | None = None
    release: anyio.Event | None = None

    async def fetch(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> ResourceContent:
        del resource, refresh
        self.fetch_calls += 1
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            await self.release.wait()
        return ResourceContent(b"content", media_type="text/plain")

    async def fetch_bytes(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> bytes:
        return (await self.fetch(resource, refresh=refresh)).data

    async def fetch_text(
        self,
        resource: ResourceRef,
        *,
        encoding: str = "utf-8",
        errors: str = "strict",
        refresh: bool = False,
    ) -> str:
        return (await self.fetch_bytes(resource, refresh=refresh)).decode(
            encoding,
            errors,
        )

    @asynccontextmanager
    async def publish(
        self,
        content: ResourceContent | InlineResource,
        *,
        suffix: str | None = None,
    ) -> AsyncIterator[PublishedResource]:
        del content, suffix
        raise AssertionError("publish is not exercised by this test double")
        yield


def _runtime(
    lifecycle: _FakeLifecycle,
    *,
    resources: _FakeResources | None = None,
    capabilities: CapabilityCatalog | None = None,
) -> RenderRuntime:
    admission = OperationAdmissionGate()
    return RenderRuntime(
        renderer=_RENDERER,
        templates=_TEMPLATES,
        resources=cast("ResourceAccess", resources or _FakeResources()),
        graphics=_GRAPHICS,
        lifecycle=lifecycle,
        operation_admission=admission,
        capabilities=capabilities,
        provider_id="fake",
    )


async def _wait_for_state(runtime: RenderRuntime, state: RuntimeState) -> None:
    while runtime.state is not state:
        await anyio.lowlevel.checkpoint()


async def test_startup_is_concurrency_safe_and_idempotent() -> None:
    lifecycle = _FakeLifecycle()
    runtime = _runtime(lifecycle)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(runtime.startup)
        task_group.start_soon(runtime.startup)
        task_group.start_soon(runtime.startup)

    assert lifecycle.startup_calls == 1
    assert runtime.state is RuntimeState.OPEN


async def test_startup_failure_is_structured_and_allows_retry() -> None:
    lifecycle = _FakeLifecycle(startup_failures=[RuntimeError("boom")])
    runtime = _runtime(lifecycle)

    with pytest.raises(ProviderLifecycleError) as captured:
        await runtime.startup()

    assert captured.value.operation == "startup"
    assert captured.value.provider_id == "fake"
    assert isinstance(captured.value.__cause__, RuntimeError)

    await runtime.startup()
    assert lifecycle.startup_calls == 2


async def test_probe_starts_once_then_delegates() -> None:
    lifecycle = _FakeLifecycle()
    runtime = _runtime(lifecycle)

    await runtime.probe()
    await runtime.probe()

    assert lifecycle.startup_calls == 1
    assert lifecycle.probe_calls == 2


async def test_close_is_idempotent_and_blocks_restart() -> None:
    lifecycle = _FakeLifecycle()
    runtime = _runtime(lifecycle)

    await runtime.startup()
    await runtime.aclose()
    await runtime.aclose()

    assert lifecycle.aclose_calls == 1
    assert runtime.state is RuntimeState.CLOSED
    with pytest.raises(RuntimeUnavailableError) as captured:
        await runtime.startup()
    assert captured.value.state == RuntimeState.CLOSED.value
    assert captured.value.operation == "startup"


async def test_failed_close_is_retryable_but_runtime_stays_closing() -> None:
    lifecycle = _FakeLifecycle(aclose_failures=[RuntimeError("cache busy")])
    runtime = _runtime(lifecycle)

    with pytest.raises(ProviderLifecycleError) as captured:
        await runtime.aclose()

    assert captured.value.operation == "aclose"
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert runtime.state is RuntimeState.CLOSING
    with pytest.raises(RuntimeUnavailableError):
        await runtime.startup()

    await runtime.aclose()
    assert lifecycle.aclose_calls == 2
    assert runtime.state is RuntimeState.CLOSED


async def test_close_drains_admitted_resource_operation() -> None:
    resources = _FakeResources(started=anyio.Event(), release=anyio.Event())
    lifecycle = _FakeLifecycle()
    runtime = _runtime(lifecycle, resources=resources)
    reference = FileResourceRef(Path("asset.txt"))
    close_finished = anyio.Event()

    async def fetch() -> None:
        await runtime.resources.fetch(reference)

    async def close() -> None:
        await runtime.aclose()
        close_finished.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(fetch)
        assert resources.started is not None
        await resources.started.wait()
        task_group.start_soon(close)
        await _wait_for_state(runtime, RuntimeState.CLOSING)

        assert runtime.state is RuntimeState.CLOSING
        assert lifecycle.aclose_calls == 0
        assert not close_finished.is_set()
        assert resources.release is not None
        resources.release.set()
        await close_finished.wait()

    assert lifecycle.aclose_calls == 1
    assert runtime.state is RuntimeState.CLOSED


async def test_close_rejects_resource_facade_retained_by_caller() -> None:
    resources = _FakeResources()
    runtime = _runtime(_FakeLifecycle(), resources=resources)
    public_resources = runtime.resources

    await runtime.aclose()

    with pytest.raises(RuntimeUnavailableError) as captured:
        await public_resources.fetch(FileResourceRef(Path("asset.txt")))
    assert captured.value.operation == "resource.fetch"
    assert resources.fetch_calls == 0


async def test_lifecycle_exception_group_is_preserved_as_cause() -> None:
    failure = ExceptionGroup(
        "cleanup failed",
        [RuntimeError("provider close failed"), RuntimeError("cache clear failed")],
    )
    runtime = _runtime(_FakeLifecycle(aclose_failures=[failure]))

    with pytest.raises(ProviderLifecycleError) as captured:
        await runtime.aclose()

    assert captured.value.__cause__ is failure


def test_runtime_exposes_only_caller_services() -> None:
    runtime = _runtime(_FakeLifecycle())

    assert runtime.renderer is _RENDERER
    assert runtime.templates is _TEMPLATES
    assert runtime.graphics is _GRAPHICS
    assert runtime.resources is runtime.resources
    assert not hasattr(runtime, "preparation")
    assert not hasattr(runtime, "extensions")


def test_runtime_capabilities_default_empty_and_support_typed_lookup() -> None:
    class _Marker:
        pass

    marker = _Marker()
    key = CapabilityKey("test.marker", _Marker)
    empty = _runtime(_FakeLifecycle())
    populated = _runtime(
        _FakeLifecycle(),
        capabilities=CapabilityCatalog().with_capability(key, marker),
    )

    assert empty.capabilities.available_names == frozenset()
    assert empty.capabilities.get(key) is None
    assert populated.capabilities.available_names == frozenset({"test.marker"})
    assert populated.capabilities.require(key) is marker
