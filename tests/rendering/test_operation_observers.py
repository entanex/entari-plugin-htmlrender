from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

import pytest

from entari_plugin_htmlrender.rendering.observers import (
    NoopOperationObserver,
    observe_operation,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from types import TracebackType


class _Context(AbstractContextManager[None]):
    def __init__(
        self,
        *,
        enter_failure: Exception | None = None,
        exit_failure: Exception | None = None,
    ) -> None:
        self.enter_failure = enter_failure
        self.exit_failure = exit_failure
        self.entered = False
        self.exit_error: BaseException | None = None

    def __enter__(self) -> None:
        if self.enter_failure is not None:
            raise self.enter_failure
        self.entered = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, traceback
        self.exit_error = exc_value
        if self.exit_failure is not None:
            raise self.exit_failure


class _Observer:
    def __init__(
        self,
        context: AbstractContextManager[None] | None = None,
        *,
        failure: Exception | None = None,
    ) -> None:
        self.context = context
        self.failure = failure
        self.calls: list[tuple[str, dict[str, str]]] = []

    def observe(
        self,
        operation: str,
        attributes: Mapping[str, str],
    ) -> AbstractContextManager[None]:
        self.calls.append((operation, dict(attributes)))
        if self.failure is not None:
            raise self.failure
        assert self.context is not None
        return self.context


def test_noop_operation_observer_wraps_a_normal_body() -> None:
    with NoopOperationObserver().observe("html_to_image", {"provider": "test"}):
        result = "completed"

    assert result == "completed"


@pytest.mark.parametrize("phase", ["observe", "enter"])
def test_observer_setup_failures_are_logged_and_do_not_block_rendering(
    phase: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    failure = RuntimeError(f"{phase} failed")
    context = _Context(enter_failure=failure if phase == "enter" else None)
    observer = _Observer(
        context,
        failure=failure if phase == "observe" else None,
    )

    with observe_operation(observer, "html_to_image", {"provider": "test"}):
        result = "rendered"

    assert result == "rendered"
    assert observer.calls == [("html_to_image", {"provider": "test"})]
    assert not context.entered
    assert f"Operation observer failed for html_to_image: {phase} failed" in caplog.text


def test_body_failure_wins_when_observer_exit_also_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body_failure = ValueError("render failed")
    context = _Context(exit_failure=RuntimeError("exit failed"))
    observer = _Observer(context)

    with (
        pytest.raises(ValueError, match="render failed") as raised,
        observe_operation(observer, "html_to_image", {}),
    ):
        raise body_failure

    assert raised.value is body_failure
    assert context.exit_error is body_failure
    assert "Operation observer failed for html_to_image: exit failed" in caplog.text


def test_observer_exit_failure_is_contained_after_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    context = _Context(exit_failure=RuntimeError("exit failed"))
    observer = _Observer(context)

    with observe_operation(observer, "html_to_image", {}):
        pass

    assert context.exit_error is None
    assert "Operation observer failed for html_to_image: exit failed" in caplog.text
