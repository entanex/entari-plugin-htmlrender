from __future__ import annotations

from typing import Literal
from typing_extensions import TypeAlias

TakumiUnsupportedFeature: TypeAlias = Literal[
    "css_import",
    "font_face",
    "javascript",
    "linked_stylesheet",
    "media_condition",
]


class TakumiBackendError(RuntimeError):
    """Internal failure raised by the Takumi adapter boundary."""

    def __init__(
        self,
        message: str,
        *,
        source: BaseException | None = None,
    ) -> None:
        self.source = source
        if source is None:
            display = message
        else:
            display = f"{message} Caused by {type(source).__name__}: {source}"
        super().__init__(display)


class TakumiInputError(TakumiBackendError):
    """A field cannot be represented safely by the native Takumi boundary."""

    def __init__(
        self,
        field: str,
        message: str,
        *,
        source: BaseException | None = None,
    ) -> None:
        self.field = field
        super().__init__(f"Invalid Takumi field {field!r}: {message}", source=source)


class TakumiRuntimeError(TakumiBackendError):
    """The Takumi runtime or session is unavailable."""


class TakumiUnsupportedError(TakumiBackendError):
    """The request requires browser behavior that Takumi cannot provide."""

    def __init__(self, feature: TakumiUnsupportedFeature, detail: str) -> None:
        self.feature = feature
        self.detail = detail
        super().__init__(detail)


class TakumiResourceError(TakumiBackendError):
    """A resource reference was not supplied as in-process bytes."""

    def __init__(
        self,
        message: str,
        *,
        reference: object | None = None,
        source: BaseException | None = None,
    ) -> None:
        self.reference = reference
        super().__init__(message, source=source)


__all__ = [
    "TakumiBackendError",
    "TakumiInputError",
    "TakumiResourceError",
    "TakumiRuntimeError",
    "TakumiUnsupportedError",
    "TakumiUnsupportedFeature",
]
