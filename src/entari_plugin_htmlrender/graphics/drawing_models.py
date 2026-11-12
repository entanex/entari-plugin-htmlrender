"""Immutable values and callback contracts for backend-native drawing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeAlias

from entari_plugin_htmlrender.errors import InvalidRenderInputError
from entari_plugin_htmlrender.rendering.models import RenderOperation

from .models import TRANSPARENT, RGBAColor


def _require_positive_int(name: str, value: object) -> int:
    if type(value) is not int:
        raise InvalidRenderInputError(
            f"{name} must be an integer",
            operation=RenderOperation.DRAWING_TO_IMAGE.value,
            field=name,
        )
    if value <= 0:
        raise InvalidRenderInputError(
            f"{name} must be positive",
            operation=RenderOperation.DRAWING_TO_IMAGE.value,
            field=name,
        )
    return value


@dataclass(frozen=True, slots=True)
class DrawingCanvas:
    """Physical-pixel dimensions and background for one native draw call."""

    width: int
    height: int
    background: RGBAColor = TRANSPARENT

    def __post_init__(self) -> None:
        _require_positive_int("width", self.width)
        _require_positive_int("height", self.height)
        if not isinstance(self.background, RGBAColor):
            raise InvalidRenderInputError(
                "background must be an RGBAColor value",
                operation=RenderOperation.DRAWING_TO_IMAGE.value,
                field="background",
            )


DrawingFunction: TypeAlias = Callable[[object, Mapping[str, object]], None]


__all__ = ["DrawingCanvas", "DrawingFunction"]
