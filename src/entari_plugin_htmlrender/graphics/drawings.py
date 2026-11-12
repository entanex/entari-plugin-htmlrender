"""Named Python drawings owned by a render runtime."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, final, runtime_checkable

from entari_plugin_htmlrender.errors import (
    CapabilityUnavailableError,
    GraphicsBackendUnavailableError,
    InvalidRenderInputError,
)
from entari_plugin_htmlrender.rendering.artifacts import RenderedImage  # noqa: TC001

from .drawing_models import DrawingCanvas, DrawingFunction
from .models import (
    DEFAULT_RASTER_ENCODE_OPTIONS,
    TRANSPARENT,
    GraphicsBackendName,
    RasterEncodeOptions,
    RGBAColor,
)

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor

    from .drawing_loader import DrawingSpec


class DrawingSourceRegistry(Protocol):
    """Host-owned source loading and dependency lifetime for named drawings."""

    @property
    def names(self) -> frozenset[str]: ...

    def spec(self, name: str) -> DrawingSpec: ...

    def lease(self, name: str) -> AbstractAsyncContextManager[DrawingFunction]: ...

    async def reload(self, name: str) -> None: ...

    async def aclose(self) -> None: ...


class DrawingRegistryFactory(Protocol):
    """Create a drawing source owner at the host composition boundary."""

    def __call__(
        self,
        definitions: Mapping[str, DrawingSpec],
        *,
        worker: WorkerExecutor,
    ) -> DrawingSourceRegistry: ...


@runtime_checkable
class DrawingRenderer(Protocol):
    """Render a configured Python drawing using a fresh native canvas."""

    @property
    def names(self) -> frozenset[str]: ...

    async def render(
        self,
        name: str,
        data: Mapping[str, object] | None = None,
        *,
        width: int,
        height: int,
        background: RGBAColor = TRANSPARENT,
        output: RasterEncodeOptions = DEFAULT_RASTER_ENCODE_OPTIONS,
    ) -> RenderedImage: ...

    async def reload(self, name: str) -> None: ...


class _DrawingBackend(Protocol):
    """Native execution after the complete drawing operation was admitted."""

    async def _draw_admitted(
        self,
        callback: DrawingFunction,
        data: Mapping[str, object],
        *,
        canvas: DrawingCanvas,
        output: RasterEncodeOptions = DEFAULT_RASTER_ENCODE_OPTIONS,
    ) -> RenderedImage: ...


def _drawing_name(name: str) -> str:
    if not isinstance(name, str) or not name or name != name.strip():
        raise InvalidRenderInputError(
            "Drawing name must be a non-empty string without outer whitespace.",
            operation="graphics.draw",
            field="name",
        )
    return name


def _drawing_data(data: Mapping[str, object] | None) -> Mapping[str, object]:
    if data is None:
        return MappingProxyType({})
    if not isinstance(data, Mapping) or any(not isinstance(key, str) for key in data):
        raise InvalidRenderInputError(
            "Drawing data must be a mapping with string keys.",
            operation="graphics.draw",
            field="data",
        )
    return MappingProxyType(dict(data))


@final
class DrawingService:
    """Lease a source generation and execute it under one admission boundary."""

    def __init__(
        self,
        registry: DrawingSourceRegistry,
        backends: Mapping[GraphicsBackendName, _DrawingBackend],
        *,
        operation_admission: OperationAdmissionGate,
        max_pixels: int,
    ) -> None:
        self._registry = registry
        self._backends = dict(backends)
        self._operation_admission = operation_admission
        self._max_pixels = max_pixels

    @property
    def names(self) -> frozenset[str]:
        return self._registry.names

    async def render(
        self,
        name: str,
        data: Mapping[str, object] | None = None,
        *,
        width: int,
        height: int,
        background: RGBAColor = TRANSPARENT,
        output: RasterEncodeOptions = DEFAULT_RASTER_ENCODE_OPTIONS,
    ) -> RenderedImage:
        async with self._operation_admission.operation("graphics.draw"):
            name = _drawing_name(name)
            canvas = DrawingCanvas(width, height, background)
            if canvas.width * canvas.height > self._max_pixels:
                raise InvalidRenderInputError(
                    f"Drawing exceeds the configured limit of {self._max_pixels} pixels.",
                    operation="graphics.draw",
                    field="canvas",
                )
            values = _drawing_data(data)
            if not isinstance(output, RasterEncodeOptions):
                raise InvalidRenderInputError(
                    "output must be a RasterEncodeOptions value.",
                    operation="graphics.draw",
                    field="output",
                )
            spec = self._registry.spec(name)
            backend = self._backends.get(spec.backend)
            if backend is None:
                raise GraphicsBackendUnavailableError(
                    spec.backend,
                    f"Install entari-plugin-htmlrender[{spec.backend}] and ensure "
                    "its native dependencies are available.",
                    retryable=False,
                )
            async with self._registry.lease(name) as callback:
                return await backend._draw_admitted(
                    callback, values, canvas=canvas, output=output
                )

    async def reload(self, name: str) -> None:
        async with self._operation_admission.operation("graphics.draw.reload"):
            await self._registry.reload(_drawing_name(name))

    async def aclose(self) -> None:
        await self._registry.aclose()


@final
class _UnavailableDrawingRenderer:
    """Compatibility default for runtimes assembled without a drawing registry."""

    def __init__(self, operation_admission: OperationAdmissionGate) -> None:
        self._operation_admission = operation_admission

    @property
    def names(self) -> frozenset[str]:
        return frozenset()

    async def render(
        self,
        name: str,
        data: Mapping[str, object] | None = None,
        *,
        width: int,
        height: int,
        background: RGBAColor = TRANSPARENT,
        output: RasterEncodeOptions = DEFAULT_RASTER_ENCODE_OPTIONS,
    ) -> RenderedImage:
        del name, data, width, height, background, output
        async with self._operation_admission.operation("graphics.draw"):
            raise CapabilityUnavailableError(
                "drawings", detail="Configure graphics.drawings before rendering."
            )

    async def reload(self, name: str) -> None:
        del name
        async with self._operation_admission.operation("graphics.draw.reload"):
            raise CapabilityUnavailableError(
                "drawings", detail="Configure graphics.drawings before reloading."
            )


__all__ = [
    "DrawingRenderer",
    "DrawingService",
]
