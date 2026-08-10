"""Stable errors exposed by neutral raster-scene capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from entari_plugin_htmlrender.errors import (
    GraphicsBackendUnavailableError,
    GraphicsError,
)

if TYPE_CHECKING:
    from .models import GraphicsBackendName


class RasterBackendExecutionError(GraphicsError):
    """A raster-scene backend failed without leaking a native exception type."""

    def __init__(
        self,
        backend: GraphicsBackendName,
        detail: str,
        *,
        source: BaseException | None = None,
    ) -> None:
        super().__init__(
            f"Graphics backend {backend!r} failed: {detail}",
            backend=backend,
            operation="raster_scene_to_image",
            retryable=False,
            source=source,
        )


__all__ = [
    "GraphicsBackendUnavailableError",
    "GraphicsError",
    "RasterBackendExecutionError",
]
