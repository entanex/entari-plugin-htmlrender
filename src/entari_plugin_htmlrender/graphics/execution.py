"""Shared admission budget for in-process raster graphics work."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, final

import anyio

from entari_plugin_htmlrender.errors import InvalidRenderInputError
from entari_plugin_htmlrender.graphics.errors import (
    DrawingBackendExecutionError,
    RasterBackendExecutionError,
)
from entari_plugin_htmlrender.graphics.models import (
    RasterEncodeOptions,
    RasterScene,
)
from entari_plugin_htmlrender.rendering.models import RenderOperation
from entari_plugin_htmlrender.rendering.observers import observe_operation

from .drawing_models import DrawingCanvas

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor

    from .drawing_models import DrawingFunction
    from .models import GraphicsBackendName


class _DrawingCallbackContractError(InvalidRenderInputError):
    """Internal marker for the callback return contract."""


@final
class RasterWorkBudget:
    """Bound per-request pixels, draw commands, and native concurrency."""

    def __init__(
        self,
        *,
        max_pixels: int,
        max_concurrency: int,
        max_commands: int = 100_000,
    ) -> None:
        if max_pixels <= 0:
            raise ValueError("max_pixels must be positive")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        if max_commands <= 0:
            raise ValueError("max_commands must be positive")
        self._max_pixels = max_pixels
        self._max_commands = max_commands
        self._max_concurrency = max_concurrency
        self._slots = anyio.Semaphore(max_concurrency)

    @property
    def max_pixels(self) -> int:
        return self._max_pixels

    @property
    def max_commands(self) -> int:
        return self._max_commands

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    @asynccontextmanager
    async def reserve(self, scene: RasterScene) -> AsyncIterator[None]:
        """Validate one scene before reserving a shared native-work slot."""
        pixels = scene.width * scene.height
        self._validate_pixels(
            pixels,
            label="scene",
            field="scene",
            operation=RenderOperation.RASTER_SCENE_TO_IMAGE,
        )
        command_count = len(scene.commands)
        if command_count > self._max_commands:
            raise InvalidRenderInputError(
                f"Raster scene contains {command_count} draw commands, exceeding "
                f"the configured limit of {self._max_commands}.",
                operation=RenderOperation.RASTER_SCENE_TO_IMAGE.value,
                field="scene.commands",
            )
        async with self._slots:
            yield

    @asynccontextmanager
    async def reserve_drawing(self, canvas: DrawingCanvas) -> AsyncIterator[None]:
        """Bound pixels and native concurrency without a command-count quota."""
        self._validate_pixels(
            canvas.width * canvas.height,
            label="drawing canvas",
            field="canvas",
            operation=RenderOperation.DRAWING_TO_IMAGE,
        )
        async with self._slots:
            yield

    def _validate_pixels(
        self,
        pixels: int,
        *,
        label: str,
        field: str,
        operation: RenderOperation,
    ) -> None:
        if pixels > self._max_pixels:
            raise InvalidRenderInputError(
                f"Raster {label} contains {pixels} pixels, exceeding the "
                f"configured limit of {self._max_pixels}.",
                operation=operation.value,
                field=field,
            )


async def rasterize_with_backend(
    backend: GraphicsBackendName,
    scene: RasterScene,
    output: RasterEncodeOptions,
    rasterize_sync: Callable[[RasterScene, RasterEncodeOptions], RenderedImage],
    *,
    worker: WorkerExecutor,
    observer: OperationObserver,
    operation_admission: OperationAdmissionGate,
    budget: RasterWorkBudget,
) -> RenderedImage:
    """Admission, budgeting, observation, and error translation for one scene.

    Backend adapters only supply their synchronous ``rasterize_sync`` body.
    """
    async with (
        operation_admission.operation(RenderOperation.RASTER_SCENE_TO_IMAGE.value),
    ):
        if not isinstance(scene, RasterScene):
            raise InvalidRenderInputError(
                "scene must be a RasterScene value.",
                operation=RenderOperation.RASTER_SCENE_TO_IMAGE.value,
                field="scene",
            )
        if not isinstance(output, RasterEncodeOptions):
            raise InvalidRenderInputError(
                "output must be a RasterEncodeOptions value.",
                operation=RenderOperation.RASTER_SCENE_TO_IMAGE.value,
                field="output",
            )
        async with budget.reserve(scene):
            with observe_operation(
                observer,
                f"graphics.{backend}.rasterize",
                {
                    "render.backend": backend,
                    "render.format": output.format,
                },
            ):
                try:
                    return await worker.run_sync(rasterize_sync, scene, output)
                except Exception as error:
                    raise RasterBackendExecutionError(
                        backend,
                        "native rasterization failed",
                        source=error,
                    ) from error


async def draw_with_backend(
    backend: GraphicsBackendName,
    callback: DrawingFunction,
    data: Mapping[str, object],
    canvas: DrawingCanvas,
    output: RasterEncodeOptions,
    draw_sync: Callable[
        [DrawingFunction, Mapping[str, object], DrawingCanvas, RasterEncodeOptions],
        RenderedImage,
    ],
    *,
    worker: WorkerExecutor,
    observer: OperationObserver,
    budget: RasterWorkBudget,
) -> RenderedImage:
    """Execute one drawing callback for an already admitted caller operation."""
    if not callable(callback):
        raise InvalidRenderInputError(
            "callback must be callable.",
            operation=RenderOperation.DRAWING_TO_IMAGE.value,
            field="callback",
        )
    if not isinstance(data, Mapping):
        raise InvalidRenderInputError(
            "data must be a mapping.",
            operation=RenderOperation.DRAWING_TO_IMAGE.value,
            field="data",
        )
    if not isinstance(canvas, DrawingCanvas):
        raise InvalidRenderInputError(
            "canvas must be a DrawingCanvas value.",
            operation=RenderOperation.DRAWING_TO_IMAGE.value,
            field="canvas",
        )
    if not isinstance(output, RasterEncodeOptions):
        raise InvalidRenderInputError(
            "output must be a RasterEncodeOptions value.",
            operation=RenderOperation.DRAWING_TO_IMAGE.value,
            field="output",
        )
    async with budget.reserve_drawing(canvas):
        with observe_operation(
            observer,
            f"graphics.{backend}.draw",
            {
                "render.backend": backend,
                "render.format": output.format,
            },
        ):
            try:
                return await worker.run_sync(
                    draw_sync,
                    callback,
                    data,
                    canvas,
                    output,
                )
            except (_DrawingCallbackContractError, DrawingBackendExecutionError):
                raise
            except Exception as error:
                raise DrawingBackendExecutionError(
                    backend,
                    "native drawing failed",
                    source=error,
                ) from error


def _reject_callback_return(backend: GraphicsBackendName) -> None:
    raise _DrawingCallbackContractError(
        f"{backend} drawing callbacks must return None.",
        operation=RenderOperation.DRAWING_TO_IMAGE.value,
        field="callback.return",
    )


def _close_awaitable(result: object) -> None:
    if not isinstance(result, Awaitable):
        return
    close = getattr(result, "close", None)
    if callable(close):
        close()


def run_drawing_callback(
    backend: GraphicsBackendName,
    callback: DrawingFunction,
    context: object,
    data: Mapping[str, object],
) -> None:
    """Invoke one synchronous callback and reject every non-``None`` result."""
    result = callback(context, data)
    if result is not None:
        _close_awaitable(result)
        _reject_callback_return(backend)


__all__ = [
    "RasterWorkBudget",
    "draw_with_backend",
    "rasterize_with_backend",
    "run_drawing_callback",
]
