"""Composition-owned selection of an in-process graphics adapter."""

from __future__ import annotations

from importlib.util import find_spec
from typing import TYPE_CHECKING, final

from entari_plugin_htmlrender.errors import (
    CapabilityUnavailableError,
    GraphicsBackendUnavailableError,
    InvalidRenderInputError,
)
from entari_plugin_htmlrender.graphics.execution import RasterWorkBudget
from entari_plugin_htmlrender.graphics.models import (
    DEFAULT_RASTER_ENCODE_OPTIONS,
    RasterEncodeOptions,
    RasterScene,
)
from entari_plugin_htmlrender.rendering.models import RenderOperation

if TYPE_CHECKING:
    from entari_plugin_htmlrender.config import GraphicsSettings
    from entari_plugin_htmlrender.graphics.models import (
        GraphicsBackendName,
    )
    from entari_plugin_htmlrender.graphics.ports import GraphicsRenderer
    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor


@final
class _UnavailableGraphicsRenderer:
    """Stable renderer shape for absent or unavailable backend selection."""

    def __init__(
        self,
        backend: GraphicsBackendName | None,
        reason: str,
        operation_admission: OperationAdmissionGate,
    ) -> None:
        self._backend = backend
        self._reason = reason
        self._operation_admission = operation_admission

    async def rasterize(
        self,
        scene: RasterScene,
        *,
        output: RasterEncodeOptions = DEFAULT_RASTER_ENCODE_OPTIONS,
    ) -> RenderedImage:
        async with self._operation_admission.operation(
            RenderOperation.RASTER_SCENE_TO_IMAGE.value
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
            if self._backend is None:
                raise CapabilityUnavailableError("graphics", detail=self._reason)
            raise GraphicsBackendUnavailableError(
                self._backend,
                self._reason,
                retryable=False,
            )


def _missing_module_reason(module: str, extra: str) -> str | None:
    try:
        available = find_spec(module) is not None
    except (ImportError, ValueError):
        available = False
    if available:
        return None
    return f"Install entari-plugin-htmlrender[{extra}] to use this backend."


def build_graphics_renderer(
    settings: GraphicsSettings,
    *,
    worker: WorkerExecutor,
    observer: OperationObserver,
    operation_admission: OperationAdmissionGate,
) -> GraphicsRenderer:
    """Bind one configured backend behind the stable graphics contract."""
    backend = settings.backend
    if backend is None:
        return _UnavailableGraphicsRenderer(
            None,
            "Configure graphics.backend before rendering raster scenes.",
            operation_admission,
        )

    budget = RasterWorkBudget(
        max_pixels=settings.max_pixels,
        max_concurrency=settings.max_concurrency,
        max_commands=settings.max_commands,
    )
    if backend == "pillow":
        reason = _missing_module_reason("PIL", "pillow")
        if reason is not None:
            return _UnavailableGraphicsRenderer(backend, reason, operation_admission)
        try:
            from entari_plugin_htmlrender.adapters.pillow import (  # noqa: PLC0415
                PillowRasterSceneRenderer,
            )
        except ImportError as error:
            return _UnavailableGraphicsRenderer(
                backend,
                f"Pillow adapter import failed: {error}",
                operation_admission,
            )
        return PillowRasterSceneRenderer(
            worker=worker,
            observer=observer,
            operation_admission=operation_admission,
            budget=budget,
        )

    if backend == "skia":
        reason = _missing_module_reason("skia", "skia")
        if reason is not None:
            return _UnavailableGraphicsRenderer(backend, reason, operation_admission)
        try:
            from entari_plugin_htmlrender.adapters.skia import (  # noqa: PLC0415
                SkiaRasterSceneRenderer,
            )
        except ImportError as error:
            return _UnavailableGraphicsRenderer(
                backend,
                f"Skia adapter import failed: {error}",
                operation_admission,
            )
        return SkiaRasterSceneRenderer(
            worker=worker,
            observer=observer,
            operation_admission=operation_admission,
            budget=budget,
        )

    return _UnavailableGraphicsRenderer(
        backend,
        "Unknown graphics backend; expected 'pillow' or 'skia'.",
        operation_admission,
    )


__all__ = ["build_graphics_renderer"]
