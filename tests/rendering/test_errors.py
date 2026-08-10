"""Stable rendering errors carry fields callers can recover from."""

from __future__ import annotations

from typing import cast

from exceptiongroup import ExceptionGroup
import pytest

from entari_plugin_htmlrender.errors import (
    ErrorCause,
    HtmlRenderError,
    InvalidRenderInputError,
    ProviderExecutionError,
    ProviderLifecycleError,
    RenderTimeoutError,
    RuntimeUnavailableError,
    UnsupportedDocumentFeatureError,
    UnsupportedOperationError,
    UnsupportedRasterOptionError,
)
from entari_plugin_htmlrender.preparation import DocumentRequirement
from entari_plugin_htmlrender.rendering.models import RenderOperation


def test_rendering_error_taxonomy_roots_at_html_render_error() -> None:
    for error_type in (
        InvalidRenderInputError,
        UnsupportedOperationError,
        UnsupportedRasterOptionError,
        UnsupportedDocumentFeatureError,
        RenderTimeoutError,
        RuntimeUnavailableError,
        ProviderExecutionError,
        ProviderLifecycleError,
    ):
        assert issubclass(error_type, HtmlRenderError)


def test_unsupported_document_feature_preserves_domain_identity() -> None:
    error = UnsupportedDocumentFeatureError(
        RenderOperation.PREPARED_HTML_TO_IMAGE.value,
        DocumentRequirement.JAVASCRIPT.value,
        provider_id="native",
    )

    assert error.operation == RenderOperation.PREPARED_HTML_TO_IMAGE.value
    assert error.feature == DocumentRequirement.JAVASCRIPT.value
    assert error.provider_id == "native"


def test_error_captures_bounded_structured_cause() -> None:
    source = RuntimeError(f"\x1b[31mnative\x1b[0m\n{'x' * 300}")

    error = ProviderExecutionError(
        "Provider failed.",
        provider_id="browser",
        operation=RenderOperation.HTML_TO_IMAGE.value,
        source=source,
    )

    assert error.message == "Provider failed."
    assert error.causes == (
        ErrorCause(
            exception_type="RuntimeError",
            message=f"native {'x' * 248}…",
            truncated=True,
        ),
    )
    assert not error.message_truncated
    assert not error.causes_truncated
    assert "\x1b" not in str(error)


def test_error_flattens_and_limits_exception_groups() -> None:
    source = ExceptionGroup(
        "native failures",
        [ValueError(str(index)) for index in range(5)],
    )

    error = ProviderLifecycleError(
        "Startup failed.",
        provider_id="browser",
        operation="startup",
        source=source,
    )

    assert error.causes == (
        ErrorCause("ExceptionGroup", "native failures"),
        ErrorCause("ValueError", "0"),
        ErrorCause("ValueError", "1"),
    )
    assert error.causes_truncated


def test_error_cause_walk_is_cycle_safe() -> None:
    first = RuntimeError("first")
    second = ValueError("second")
    first.__cause__ = second
    second.__cause__ = first

    error = ProviderExecutionError(
        "Provider failed.",
        provider_id="browser",
        operation=RenderOperation.HTML_TO_IMAGE.value,
        source=first,
    )

    assert error.causes == (
        ErrorCause("RuntimeError", "first"),
        ErrorCause("ValueError", "second"),
    )
    assert not error.causes_truncated


def test_nested_detailed_error_respects_outer_cause_budget() -> None:
    nested = ProviderExecutionError(
        "Native failures.",
        provider_id="browser",
        operation=RenderOperation.HTML_TO_IMAGE.value,
        source=ExceptionGroup(
            "native failures",
            [ValueError(str(index)) for index in range(5)],
        ),
    )
    wrapper = RuntimeError("provider wrapper")
    wrapper.__cause__ = nested

    error = ProviderLifecycleError(
        "Startup failed.",
        provider_id="browser",
        operation="startup",
        source=wrapper,
    )

    assert error.causes == (
        ErrorCause("RuntimeError", "provider wrapper"),
        ErrorCause("ExceptionGroup", "native failures"),
        ErrorCause("ValueError", "0"),
    )
    assert error.causes_truncated


@pytest.mark.parametrize("feature", ["", None, 1])
def test_unsupported_document_feature_rejects_unstable_identity(
    feature: object,
) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        UnsupportedDocumentFeatureError(
            RenderOperation.PREPARED_HTML_TO_IMAGE.value,
            cast("str", feature),
        )
