"""Takumi managed-session contract and observation tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

import anyio
import pytest

from entari_plugin_htmlrender.adapters.takumi import (
    TakumiConfig,
    TakumiSessionAdapter,
)
from entari_plugin_htmlrender.adapters.takumi import (
    capabilities as capabilities_module,
)
from entari_plugin_htmlrender.adapters.takumi.capabilities import (
    TakumiCapabilityAdapter,
)
from entari_plugin_htmlrender.adapters.takumi.errors import (
    TakumiInputError,
    TakumiResourceError,
    TakumiRuntimeError,
    TakumiUnsupportedError,
)
from entari_plugin_htmlrender.adapters.takumi.runtime import TakumiRuntimeState
from entari_plugin_htmlrender.capabilities import TAKUMI, TakumiCapability
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    ProviderExecutionError,
    ResourceFetchError,
    RuntimeUnavailableError,
    UnsupportedDocumentFeatureError,
)
from entari_plugin_htmlrender.rendering import OperationAdmissionGate
from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog
from entari_plugin_htmlrender.runtime import RenderRuntime, RuntimeState
from tests.adapters.takumi.helpers import resource_service

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from pytest_mock import MockerFixture

    from entari_plugin_htmlrender.adapters._lease import ExecutionLeaseProvider
    from entari_plugin_htmlrender.adapters.takumi.types import NativeRenderer
    from entari_plugin_htmlrender.graphics import GraphicsRenderer
    from entari_plugin_htmlrender.rendering.contracts import (
        HtmlRenderer,
        TemplateRenderer,
    )
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.ports import ResourceAccess
    from tests.adapters.conftest import RecordingOperationObserver


class _Renderer:
    pass


class _LeaseSource:
    def __init__(self, state: object) -> None:
        self._state = state

    @asynccontextmanager
    async def lease(self) -> AsyncIterator[object]:
        yield self._state


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


def _state() -> TakumiRuntimeState:
    return TakumiRuntimeState(
        renderer=cast("NativeRenderer", _Renderer()),
        limiter=anyio.Semaphore(1),
        config=TakumiConfig(),
        resources=resource_service(),
    )


def _capability(
    state: object,
    observer: OperationObserver,
    *,
    operation_admission: OperationAdmissionGate | None = None,
) -> TakumiCapabilityAdapter:
    leases = cast(
        "ExecutionLeaseProvider[TakumiRuntimeState]",
        _LeaseSource(state),
    )
    return TakumiCapabilityAdapter(
        leases,
        observer,
        operation_admission=operation_admission or OperationAdmissionGate(),
    )


def test_takumi_capability_key_identity() -> None:
    assert TAKUMI.name == "takumi"
    assert TAKUMI.interface is TakumiCapability


async def test_managed_session_telemetry_covers_success_and_error_without_content(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    state = _state()
    call_document = mocker.patch.object(
        TakumiRuntimeState, "call_document", new=mocker.AsyncMock(return_value="<svg/>")
    )
    session = TakumiSessionAdapter(state, operation_observer)

    assert await session.render_svg_html("<div></div>") == "<svg/>"
    assert call_document.await_count == 1
    assert operation_observer.operations[-1] == (
        "takumi.session.render_svg_html",
        {"render.backend": "takumi"},
        "success",
    )

    call_document.side_effect = ValueError("native failure")
    with pytest.raises(ProviderExecutionError, match="native failure") as raised:
        await session.render_svg_html("<div></div>")
    assert raised.value.provider_id == "takumi"
    assert raised.value.operation == "takumi.render_svg_html"
    assert operation_observer.operations[-1] == (
        "takumi.session.render_svg_html",
        {"render.backend": "takumi"},
        "error",
    )


@pytest.mark.parametrize(
    ("error", "expected_type"),
    [
        pytest.param(
            TakumiInputError("images[0]", "invalid image"),
            InvalidRenderInputError,
            id="input",
        ),
        pytest.param(
            TakumiResourceError(
                "missing image",
                reference="asset://missing",
            ),
            ResourceFetchError,
            id="resource",
        ),
        pytest.param(
            TakumiUnsupportedError("javascript", "scripts are unsupported"),
            UnsupportedDocumentFeatureError,
            id="unsupported",
        ),
        pytest.param(
            TakumiRuntimeError("native runtime failed"),
            ProviderExecutionError,
            id="runtime",
        ),
        pytest.param(
            TypeError("invalid duck input"),
            InvalidRenderInputError,
            id="raw-type-error",
        ),
        pytest.param(
            ValueError("unknown adapter failure"),
            ProviderExecutionError,
            id="unknown-error",
        ),
    ],
)
async def test_managed_session_translates_every_adapter_failure_class(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
    error: Exception,
    expected_type: type[Exception],
) -> None:
    state = _state()
    mocker.patch.object(
        TakumiRuntimeState,
        "call_document",
        new=mocker.AsyncMock(side_effect=error),
    )
    session = TakumiSessionAdapter(state, operation_observer)

    with pytest.raises(expected_type) as raised:
        await session.render_svg_html("<div></div>")

    assert isinstance(
        raised.value,
        (
            InvalidRenderInputError,
            ProviderExecutionError,
            ResourceFetchError,
            UnsupportedDocumentFeatureError,
        ),
    )
    translated = raised.value
    assert translated.__cause__ is error
    assert translated.operation == "takumi.render_svg_html"
    if isinstance(error, TakumiInputError):
        assert isinstance(raised.value, InvalidRenderInputError)
        assert raised.value.field == "images[0]"
    elif isinstance(error, TakumiResourceError):
        assert isinstance(raised.value, ResourceFetchError)
        assert raised.value.reference == "asset://missing"
    elif isinstance(error, TakumiUnsupportedError):
        assert isinstance(raised.value, UnsupportedDocumentFeatureError)
        assert raised.value.feature == "javascript"
    elif isinstance(raised.value, ProviderExecutionError):
        assert raised.value.provider_id == "takumi"


async def test_managed_lease_translates_runtime_validation_only(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    error = TakumiRuntimeError("invalid runtime state")
    mocker.patch.object(
        capabilities_module,
        "require_runtime_state",
        side_effect=error,
    )
    capability = _capability(object(), operation_observer)

    with pytest.raises(ProviderExecutionError) as raised:
        async with capability.lease_session():
            pytest.fail("invalid runtime state must not be yielded")

    assert raised.value.__cause__ is error
    assert raised.value.provider_id == "takumi"
    assert raised.value.operation == "takumi.lease_session"


async def test_managed_lease_does_not_translate_caller_body_errors(
    operation_observer: RecordingOperationObserver,
) -> None:
    capability = _capability(_state(), operation_observer)

    with pytest.raises(TypeError, match="caller failure"):
        async with capability.lease_session():
            raise TypeError("caller failure")


async def test_native_lease_preserves_raw_runtime_failure(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    error = TakumiRuntimeError("raw native failure")
    mocker.patch.object(
        capabilities_module,
        "require_runtime_state",
        side_effect=error,
    )
    capability = _capability(object(), operation_observer)

    with pytest.raises(TakumiRuntimeError) as raised:
        async with capability.lease_native_renderer():
            pytest.fail("invalid runtime state must not be yielded")

    assert raised.value is error


@pytest.mark.parametrize(
    ("lease_kind", "operation"),
    [
        ("session", "takumi.lease_session"),
        ("native", "takumi.lease_native_renderer"),
    ],
)
async def test_retained_capability_reports_runtime_closing_and_closed(
    operation_observer: RecordingOperationObserver,
    lease_kind: str,
    operation: str,
) -> None:
    admission = OperationAdmissionGate()
    capability = _capability(
        _state(),
        operation_observer,
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
        capabilities=CapabilityCatalog().with_capability(TAKUMI, capability),
        provider_id="takumi",
    )
    retained = runtime.capabilities.takumi

    def lease_context() -> AbstractAsyncContextManager[object]:
        if lease_kind == "session":
            return retained.lease_session()
        return retained.lease_native_renderer()

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
