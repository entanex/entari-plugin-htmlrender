"""Lowest-level public error root shared by all architectural layers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import final

from exceptiongroup import BaseExceptionGroup

_MAX_MESSAGE_LENGTH = 512
_MAX_CAUSE_MESSAGE_LENGTH = 256
_MAX_EXCEPTION_TYPE_LENGTH = 96
_MAX_CAUSES = 3
_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _clip_text(value: str, limit: int) -> tuple[str, bool]:
    normalized = " ".join(_ANSI_ESCAPE.sub("", value).split())
    if len(normalized) <= limit:
        return normalized, False
    return f"{normalized[: limit - 1].rstrip()}…", True


@final
@dataclass(frozen=True, slots=True)
class ErrorCause:
    """Bounded information copied from one underlying exception."""

    exception_type: str
    message: str
    truncated: bool = False


def _capture_cause(error: BaseException, message: str | None = None) -> ErrorCause:
    exception_type, type_truncated = _clip_text(
        type(error).__name__,
        _MAX_EXCEPTION_TYPE_LENGTH,
    )
    detail, message_truncated = _clip_text(
        str(error) if message is None else message,
        _MAX_CAUSE_MESSAGE_LENGTH,
    )
    return ErrorCause(
        exception_type=exception_type,
        message=detail,
        truncated=type_truncated or message_truncated,
    )


def _captured_causes(error: BaseException) -> tuple[tuple[ErrorCause, ...], bool]:
    if isinstance(error, _DetailedError) and error.causes:
        return error.causes, error.causes_truncated

    pending: list[BaseException] = [error]
    causes: list[ErrorCause] = []
    causes_truncated = False
    seen: set[int] = set()
    while pending and len(causes) < _MAX_CAUSES:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(current, BaseExceptionGroup):
            causes.append(_capture_cause(current, current.message))
            pending.extend(reversed(current.exceptions))
            continue
        if isinstance(current, _DetailedError) and current.causes:
            available = _MAX_CAUSES - len(causes)
            causes.extend(current.causes[:available])
            if current.causes_truncated or len(current.causes) > available:
                causes_truncated = True
            continue
        causes.append(_capture_cause(current))
        nested = current.__cause__
        if nested is None and not current.__suppress_context__:
            nested = current.__context__
        if nested is not None:
            pending.append(nested)
    return tuple(causes), causes_truncated or bool(pending)


class _DetailedError(Exception):
    message: str
    message_truncated: bool
    causes: tuple[ErrorCause, ...]
    causes_truncated: bool

    def __init__(
        self,
        message: str,
        *,
        source: BaseException | None = None,
    ) -> None:
        self.message, self.message_truncated = _clip_text(
            message,
            _MAX_MESSAGE_LENGTH,
        )
        if source is None:
            self.causes = ()
            self.causes_truncated = False
        else:
            self.causes, self.causes_truncated = _captured_causes(source)
        super().__init__(self._display_message())

    def _display_message(self) -> str:
        if not self.causes:
            return self.message
        details = "; ".join(
            (
                f"{cause.exception_type}: {cause.message}"
                if cause.message
                else cause.exception_type
            )
            for cause in self.causes
        )
        if self.causes_truncated:
            details = f"{details}; …"
        return f"{self.message} Caused by {details}"


class HtmlRenderError(_DetailedError):
    """Root of every stable failure exposed to HTMLRender callers."""


class InvalidRenderInputError(HtmlRenderError):
    """A caller supplied an invalid value for one rendering operation."""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        field: str | None = None,
        source: BaseException | None = None,
    ) -> None:
        self.operation = operation
        self.field = field
        super().__init__(message, source=source)


class UnsupportedOperationError(HtmlRenderError):
    """The selected composition does not implement a requested operation."""

    def __init__(
        self,
        operation: str,
        *,
        provider_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.operation = operation
        self.provider_id = provider_id
        target = (
            "the current composition"
            if provider_id is None
            else f"provider {provider_id!r}"
        )
        message = f"Operation {operation!r} is not supported by {target}."
        if detail:
            message = f"{message} {detail}"
        super().__init__(message)


class UnsupportedRasterOptionError(UnsupportedOperationError):
    """A portable raster option is unsupported by the selected provider."""

    def __init__(
        self,
        operation: str,
        option: str,
        *,
        provider_id: str | None = None,
        value: object | None = None,
    ) -> None:
        self.option = option
        self.value = value
        detail = f"Raster option {option!r} is not supported."
        super().__init__(
            operation,
            provider_id=provider_id,
            detail=detail,
        )


class UnsupportedDocumentFeatureError(UnsupportedOperationError):
    """A prepared document uses a stable feature the provider cannot deliver."""

    def __init__(
        self,
        operation: str,
        feature: str,
        *,
        provider_id: str | None = None,
    ) -> None:
        if not isinstance(feature, str) or not feature:
            raise ValueError("document feature must be a non-empty string")
        self.feature = feature
        super().__init__(
            operation,
            provider_id=provider_id,
            detail=f"Document feature {feature!r} is not supported.",
        )


class RenderTimeoutError(HtmlRenderError):
    """A complete public operation exceeded its caller-visible deadline."""

    def __init__(
        self,
        operation: str,
        timeout_seconds: float,
        *,
        source: BaseException | None = None,
    ) -> None:
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Operation {operation!r} timed out after {timeout_seconds} seconds.",
            source=source,
        )


class RenderOutputLimitError(HtmlRenderError):
    """A provider result exceeded a configured output safety limit."""

    def __init__(
        self,
        operation: str,
        limit: str,
        *,
        actual: int,
        maximum: int,
    ) -> None:
        self.operation = operation
        self.limit = limit
        self.actual = actual
        self.maximum = maximum
        super().__init__(
            f"Rendered output {limit} is {actual}, exceeding the configured "
            f"maximum of {maximum}."
        )


class RuntimeUnavailableError(HtmlRenderError):
    """The runtime state does not admit new caller operations."""

    def __init__(self, state: str, *, operation: str | None = None) -> None:
        self.state = state
        self.operation = operation
        operation_detail = "" if operation is None else f" for {operation!r}"
        super().__init__(
            f"Render runtime is unavailable{operation_detail}: current state is "
            f"{state!r}."
        )


class CapabilityUnavailableError(HtmlRenderError):
    """An optional typed capability is absent from the composition."""

    def __init__(self, capability: str, *, detail: str | None = None) -> None:
        self.capability = capability
        message = f"Capability {capability!r} is not available."
        if detail:
            message = f"{message} {detail}"
        super().__init__(message)


class GraphicsError(HtmlRenderError):
    """Base for failures attributed to one configured graphics backend."""

    def __init__(
        self,
        message: str,
        *,
        backend: str | None,
        operation: str,
        retryable: bool = False,
        source: BaseException | None = None,
    ) -> None:
        self.backend = backend
        self.operation = operation
        self.retryable = retryable
        super().__init__(message, source=source)


class GraphicsBackendUnavailableError(GraphicsError):
    """The selected in-process graphics backend cannot run."""

    def __init__(
        self,
        backend: str,
        reason: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.backend = backend
        self.reason = reason
        super().__init__(
            f"Graphics backend {backend!r} is unavailable: {reason}",
            backend=backend,
            operation="raster_scene_to_image",
            retryable=retryable,
        )


class ProviderError(HtmlRenderError):
    """Base for failures attributed to one selected render provider."""

    def __init__(
        self,
        message: str,
        *,
        provider_id: str | None,
        operation: str | None = None,
        retryable: bool = False,
        source: BaseException | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.operation = operation
        self.retryable = retryable
        super().__init__(message, source=source)


class ProviderSelectionError(ProviderError):
    """Provider discovery, conflict resolution, or configuration failed."""


class ProviderNotFoundError(ProviderSelectionError):
    """The configured provider ID did not resolve to an installed provider."""


class ProviderConflictError(ProviderSelectionError):
    """More than one provider claimed the same stable provider ID."""


class ProviderConfigurationError(ProviderSelectionError):
    """The selected provider rejected its configuration."""


class ProviderUnavailableError(ProviderError):
    """The provider exists but cannot run in the current environment."""

    def __init__(
        self,
        provider_id: str,
        reason: str,
        *,
        operation: str = "check_availability",
        retryable: bool = False,
        source: BaseException | None = None,
    ) -> None:
        self.reason = reason
        super().__init__(
            f"Provider {provider_id!r} is unavailable: {reason}",
            provider_id=provider_id,
            operation=operation,
            retryable=retryable,
            source=source,
        )


class ProviderExecutionError(ProviderError):
    """A provider failed after execution of a render operation began."""


class ProviderLifecycleError(ProviderError):
    """A provider failed during startup, probe, or shutdown."""


class ResourceError(HtmlRenderError):
    """Base for failures while fetching or publishing one resource."""

    def __init__(
        self,
        message: str,
        *,
        reference: object | None,
        operation: str,
        retryable: bool = False,
        source: BaseException | None = None,
    ) -> None:
        self.reference = reference
        self.operation = operation
        self.retryable = retryable
        super().__init__(message, source=source)


class ResourceNotFoundError(ResourceError):
    """The referenced resource does not exist."""


class ResourceAccessDeniedError(ResourceError):
    """Policy or remote authorization denied access to the resource."""


class ResourceTooLargeError(ResourceError):
    """A resource exceeded an explicit byte limit."""

    def __init__(
        self,
        message: str,
        *,
        reference: object | None,
        operation: str,
        actual_size: int | None,
        maximum_size: int,
        source: BaseException | None = None,
    ) -> None:
        self.actual_size = actual_size
        self.maximum_size = maximum_size
        super().__init__(
            message,
            reference=reference,
            operation=operation,
            source=source,
        )


class ResourceFetchError(ResourceError):
    """A file or network transport failed to fetch resource content."""


class ResourceNetworkError(ResourceFetchError):
    """Name resolution, connection, or TLS transport failed."""


class ResourceTimeoutError(ResourceFetchError):
    """A resource operation exceeded its end-to-end deadline."""

    def __init__(
        self,
        message: str,
        *,
        reference: object | None,
        operation: str,
        timeout_seconds: float,
        source: BaseException | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            message,
            reference=reference,
            operation=operation,
            retryable=True,
            source=source,
        )


class ResourceRemoteResponseError(ResourceFetchError):
    """A remote server returned a final HTTP response that was not usable."""

    def __init__(
        self,
        message: str,
        *,
        reference: object | None,
        operation: str,
        status_code: int,
        retryable: bool = False,
        source: BaseException | None = None,
    ) -> None:
        self.status_code = status_code
        super().__init__(
            message,
            reference=reference,
            operation=operation,
            retryable=retryable,
            source=source,
        )


class ResourceAuthenticationError(ResourceRemoteResponseError):
    """A remote server rejected the request's authentication or authority."""


class ResourcePublishError(ResourceError):
    """A publication transport failed to expose resource content."""


__all__ = [
    "CapabilityUnavailableError",
    "ErrorCause",
    "GraphicsBackendUnavailableError",
    "GraphicsError",
    "HtmlRenderError",
    "InvalidRenderInputError",
    "ProviderConfigurationError",
    "ProviderConflictError",
    "ProviderError",
    "ProviderExecutionError",
    "ProviderLifecycleError",
    "ProviderNotFoundError",
    "ProviderSelectionError",
    "ProviderUnavailableError",
    "RenderOutputLimitError",
    "RenderTimeoutError",
    "ResourceAccessDeniedError",
    "ResourceAuthenticationError",
    "ResourceError",
    "ResourceFetchError",
    "ResourceNetworkError",
    "ResourceNotFoundError",
    "ResourcePublishError",
    "ResourceRemoteResponseError",
    "ResourceTimeoutError",
    "ResourceTooLargeError",
    "RuntimeUnavailableError",
    "UnsupportedDocumentFeatureError",
    "UnsupportedOperationError",
    "UnsupportedRasterOptionError",
]
