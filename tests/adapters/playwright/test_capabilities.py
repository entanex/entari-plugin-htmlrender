from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import anyio
from anyio.lowlevel import checkpoint
from playwright.async_api import Browser, Page, Playwright
import pytest

from entari_plugin_htmlrender.adapters._lease import ExecutionLeaseProvider
from entari_plugin_htmlrender.adapters.playwright.capabilities import (
    PlaywrightCapabilityAdapter,
)
from entari_plugin_htmlrender.adapters.playwright.render import (
    PlaywrightLease,
    PlaywrightMode,
)
from entari_plugin_htmlrender.capabilities import (
    PLAYWRIGHT,
    PlaywrightCapability,
)
from entari_plugin_htmlrender.errors import RuntimeUnavailableError
from entari_plugin_htmlrender.rendering import OperationAdmissionGate
from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog
from entari_plugin_htmlrender.rendering.errors import ProviderLifecycleError
from entari_plugin_htmlrender.runtime import RenderRuntime, RuntimeState
from tests.adapters.conftest import RecordingOperationObserver

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
    from contextlib import AbstractAsyncContextManager

    from pytest_mock import MockerFixture

    from entari_plugin_htmlrender.errors import ProviderError
    from entari_plugin_htmlrender.graphics import GraphicsRenderer
    from entari_plugin_htmlrender.rendering.contracts import (
        HtmlRenderer,
        TemplateRenderer,
    )
    from entari_plugin_htmlrender.resources.ports import ResourceAccess


@dataclass(slots=True)
class _LeaseState:
    lease: PlaywrightLease
    alive: bool = True


class _BlockingLifecycle:
    def __init__(self) -> None:
        self.close_entered = anyio.Event()
        self.release_close = anyio.Event()

    async def startup(self) -> None:
        return None

    async def probe(self) -> None:
        return None

    async def aclose(self) -> None:
        self.close_entered.set()
        await self.release_close.wait()


def test_playwright_capability_key_identity() -> None:
    assert PLAYWRIGHT.name == "playwright"
    assert PLAYWRIGHT.interface is PlaywrightCapability


@contextmanager
def _translate(
    operation: str,
    error_type: type[ProviderError],
) -> Iterator[None]:
    try:
        yield
    except Exception as error:
        raise error_type(
            f"{operation} failed.",
            provider_id="playwright",
            operation=operation,
            source=error,
        ) from error


def _capability(
    *,
    close: Callable[[PlaywrightLease], Awaitable[None]],
    operation_admission: OperationAdmissionGate | None = None,
) -> tuple[
    PlaywrightCapabilityAdapter,
    _LeaseState,
    ExecutionLeaseProvider[PlaywrightLease],
    RecordingOperationObserver,
]:
    state = _LeaseState(
        PlaywrightLease(
            playwright=object.__new__(Playwright),
            browser=object.__new__(Browser),
            mode=PlaywrightMode.LOCAL,
        )
    )

    async def create() -> PlaywrightLease:
        return state.lease

    async def close_lease(lease: PlaywrightLease) -> None:
        try:
            await close(lease)
        finally:
            state.alive = False

    observer = RecordingOperationObserver()
    leases = ExecutionLeaseProvider(
        create=create,
        is_alive=lambda _: state.alive,
        close=close_lease,
        provider_id="playwright",
        observer=observer,
        translate=_translate,
        observation_attributes={"render.backend": "playwright"},
    )
    capability = PlaywrightCapabilityAdapter(
        leases,
        observer,
        operation_admission=operation_admission or OperationAdmissionGate(),
    )
    return capability, state, leases, observer


async def test_page_context_holds_runtime_lease_until_page_closes(
    mocker: MockerFixture,
) -> None:
    order: list[str] = []

    async def close(lease: PlaywrightLease) -> None:
        del lease
        order.append("runtime-close")

    capability, _, leases, observer = _capability(close=close)
    page = object.__new__(Page)

    @asynccontextmanager
    async def open_page_context(
        _context: object,
        **kwargs: object,
    ) -> AsyncIterator[Page]:
        assert kwargs == {}
        try:
            yield page
        finally:
            order.append("page-close")

    mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright._page.PageContext.open",
        open_page_context,
    )
    async with (
        anyio.create_task_group() as task_group,
        capability.lease_page() as opened,
    ):
        assert opened is page
        task_group.start_soon(leases.aclose)
        await checkpoint()
        assert order == []

    assert order == ["page-close", "runtime-close"]
    assert (
        "playwright.native.page",
        {"render.backend": "playwright", "render.access": "native"},
        "success",
    ) in observer.operations


async def test_browser_context_yields_native_instance_and_tracks_lease() -> None:
    async def close(lease: PlaywrightLease) -> None:
        del lease

    capability, state, leases, observer = _capability(close=close)

    async with (
        anyio.create_task_group() as task_group,
        capability.lease_browser() as browser,
    ):
        assert browser is state.lease.browser
        task_group.start_soon(leases.aclose)
        await checkpoint()
        assert state.alive is True

    assert state.alive is False
    assert (
        "playwright.native.browser",
        {"render.backend": "playwright", "render.access": "native"},
        "success",
    ) in observer.operations


async def test_browser_capability_close_waits_for_first_lease_create() -> None:
    create_entered = anyio.Event()
    finish_create = anyio.Event()
    close_started = anyio.Event()
    close_returned = anyio.Event()
    errors: list[ProviderLifecycleError] = []
    closed: list[PlaywrightLease] = []
    lease = PlaywrightLease(
        playwright=object.__new__(Playwright),
        browser=object.__new__(Browser),
        mode=PlaywrightMode.LOCAL,
    )

    async def create() -> PlaywrightLease:
        create_entered.set()
        await finish_create.wait()
        return lease

    async def close(created: PlaywrightLease) -> None:
        closed.append(created)

    leases = ExecutionLeaseProvider(
        create=create,
        is_alive=lambda _: True,
        close=close,
        provider_id="playwright",
        observer=RecordingOperationObserver(),
        translate=_translate,
        observation_attributes={"render.backend": "playwright"},
    )
    capability = PlaywrightCapabilityAdapter(
        leases,
        RecordingOperationObserver(),
        operation_admission=OperationAdmissionGate(),
    )

    async def acquire_browser() -> None:
        try:
            async with capability.lease_browser():
                raise AssertionError("A browser created after close was admitted")
        except ProviderLifecycleError as error:
            errors.append(error)

    async def close_provider() -> None:
        close_started.set()
        await leases.aclose()
        close_returned.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(acquire_browser)
        await create_entered.wait()
        task_group.start_soon(close_provider)
        await close_started.wait()
        await checkpoint()

        assert not close_returned.is_set()
        assert closed == []
        finish_create.set()
        await close_returned.wait()
        assert closed == [lease]

    assert len(errors) == 1
    assert errors[0].provider_id == "playwright"
    assert errors[0].operation == "lease"


@pytest.mark.parametrize(
    ("lease_kind", "operation"),
    [
        ("page", "playwright.lease_page"),
        ("browser", "playwright.lease_browser"),
    ],
)
async def test_retained_capability_reports_runtime_closing_and_closed(
    lease_kind: str,
    operation: str,
) -> None:
    async def close(lease: PlaywrightLease) -> None:
        del lease

    admission = OperationAdmissionGate()
    capability, _, leases, _ = _capability(
        close=close,
        operation_admission=admission,
    )
    lifecycle = _BlockingLifecycle()
    runtime = RenderRuntime(
        renderer=cast("HtmlRenderer", object()),
        templates=cast("TemplateRenderer", object()),
        resources=cast("ResourceAccess", object()),
        graphics=cast("GraphicsRenderer", object()),
        lifecycle=lifecycle,
        operation_admission=admission,
        capabilities=CapabilityCatalog().with_capability(PLAYWRIGHT, capability),
        provider_id="playwright",
    )
    retained = runtime.capabilities.playwright

    def lease_context() -> AbstractAsyncContextManager[object]:
        if lease_kind == "page":
            return retained.lease_page()
        return retained.lease_browser()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(runtime.aclose)
        await lifecycle.close_entered.wait()
        assert runtime.state is RuntimeState.CLOSING
        with pytest.raises(RuntimeUnavailableError) as closing:
            async with lease_context():
                pytest.fail("a closing runtime must not issue a capability lease")
        assert closing.value.state == "closing"
        assert closing.value.operation == operation
        lifecycle.release_close.set()

    assert runtime.state is RuntimeState.CLOSED

    with pytest.raises(RuntimeUnavailableError) as closed:
        async with lease_context():
            pytest.fail("a closed runtime must not issue a capability lease")
    assert closed.value.state == "closed"
    assert closed.value.operation == operation

    await leases.aclose()
