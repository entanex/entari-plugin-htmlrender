from __future__ import annotations

from entari_plugin_htmlrender.errors import (
    CapabilityUnavailableError,
    HtmlRenderError,
    InvalidRenderInputError,
    ProviderUnavailableError,
    RenderTimeoutError,
    ResourceTooLargeError,
    RuntimeUnavailableError,
    UnsupportedDocumentFeatureError,
    UnsupportedOperationError,
    UnsupportedRasterOptionError,
)
from entari_plugin_htmlrender.rendering.models import RenderOperation


def test_input_error_exposes_operation_and_field() -> None:
    error = InvalidRenderInputError(
        "Raster width must be positive.",
        operation=RenderOperation.HTML_TO_IMAGE.value,
        field="raster.width",
    )

    assert isinstance(error, HtmlRenderError)
    assert error.operation == RenderOperation.HTML_TO_IMAGE.value
    assert error.field == "raster.width"


def test_unsupported_operation_exposes_provider_identity() -> None:
    error = UnsupportedOperationError(
        RenderOperation.HTML_TO_IMAGE.value,
        provider_id="text-only",
    )

    assert error.operation == RenderOperation.HTML_TO_IMAGE.value
    assert error.provider_id == "text-only"


def test_timeout_exposes_deadline() -> None:
    error = RenderTimeoutError(RenderOperation.MARKDOWN_TO_IMAGE.value, 2.5)

    assert error.operation == RenderOperation.MARKDOWN_TO_IMAGE.value
    assert error.timeout_seconds == 2.5


def test_runtime_unavailable_exposes_state() -> None:
    error = RuntimeUnavailableError("closing", operation="fetch")

    assert error.state == "closing"
    assert error.operation == "fetch"


def test_provider_unavailable_exposes_recovery_fields() -> None:
    error = ProviderUnavailableError(
        "playwright",
        "browser executable is not installed",
        retryable=False,
    )

    assert error.provider_id == "playwright"
    assert error.operation == "check_availability"
    assert error.reason == "browser executable is not installed"
    assert error.retryable is False


def test_resource_limit_exposes_actual_and_maximum_size() -> None:
    error = ResourceTooLargeError(
        "Resource exceeds the configured fetch limit.",
        reference="https://cdn.example/image.png",
        operation="fetch",
        actual_size=2048,
        maximum_size=1024,
    )

    assert error.reference == "https://cdn.example/image.png"
    assert error.operation == "fetch"
    assert error.actual_size == 2048
    assert error.maximum_size == 1024


def test_capability_unavailable_is_not_an_unsupported_render_operation() -> None:
    error = CapabilityUnavailableError("playwright")

    assert error.capability == "playwright"
    assert not isinstance(error, UnsupportedOperationError)


def test_unsupported_raster_option_exposes_recovery_identity() -> None:
    error = UnsupportedRasterOptionError(
        RenderOperation.HTML_TO_IMAGE.value,
        "device_pixel_ratio",
        provider_id="takumi",
        value=8.0,
    )

    assert isinstance(error, UnsupportedOperationError)
    assert error.operation == RenderOperation.HTML_TO_IMAGE.value
    assert error.provider_id == "takumi"
    assert error.option == "device_pixel_ratio"
    assert error.value == 8.0


def test_unsupported_feature_exposes_stable_identity() -> None:
    error = UnsupportedDocumentFeatureError(
        RenderOperation.PREPARED_HTML_TO_IMAGE.value,
        "browser_css",
        provider_id="takumi",
    )

    assert isinstance(error, UnsupportedOperationError)
    assert error.feature == "browser_css"
