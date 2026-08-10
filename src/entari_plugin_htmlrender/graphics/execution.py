"""Shared admission budget for in-process raster scene work."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, final

import anyio

from entari_plugin_htmlrender.errors import InvalidRenderInputError
from entari_plugin_htmlrender.graphics.errors import RasterBackendExecutionError
from entari_plugin_htmlrender.graphics.models import (
    RasterEncodeOptions,
    RasterScene,
)
from entari_plugin_htmlrender.rendering.models import RenderOperation
from entari_plugin_htmlrender.rendering.observers import observe_operation

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor

    from .models import GraphicsBackendName


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
        if pixels > self._max_pixels:
            raise InvalidRenderInputError(
                f"Raster scene contains {pixels} pixels, exceeding the configured "
                f"limit of {self._max_pixels}.",
                operation=RenderOperation.RASTER_SCENE_TO_IMAGE.value,
                field="scene",
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


__all__ = ["RasterWorkBudget", "rasterize_with_backend"]
