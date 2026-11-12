"""Composition-owned selection of independent in-process graphics adapters."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from typing import TYPE_CHECKING, cast, final

from entari_plugin_htmlrender.errors import (
    CapabilityUnavailableError,
    GraphicsBackendUnavailableError,
    InvalidRenderInputError,
)
from entari_plugin_htmlrender.graphics import (
    PILLOW_RASTER_SCENE_RENDERER,
    SKIA_RASTER_SCENE_RENDERER,
)
from entari_plugin_htmlrender.graphics.drawing_loader import (
    DrawingRegistry,
    DrawingSpec,
)
from entari_plugin_htmlrender.graphics.drawings import DrawingService
from entari_plugin_htmlrender.graphics.execution import RasterWorkBudget
from entari_plugin_htmlrender.graphics.models import (
    DEFAULT_RASTER_ENCODE_OPTIONS,
    RasterEncodeOptions,
    RasterScene,
)
from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog
from entari_plugin_htmlrender.rendering.models import RenderOperation

if TYPE_CHECKING:
    from entari_plugin_htmlrender.config import GraphicsSettings
    from entari_plugin_htmlrender.graphics.drawings import (
        DrawingRegistryFactory,
        _DrawingBackend,
    )
    from entari_plugin_htmlrender.graphics.models import GraphicsBackendName
    from entari_plugin_htmlrender.graphics.ports import GraphicsRenderer
    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor


@final
class _UnavailableGraphicsRenderer:
    """Stable renderer shape for absent or unavailable primary selection."""

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


@dataclass(frozen=True, slots=True)
class GraphicsComposition:
    """Primary compatibility renderer plus independently available backends."""

    primary: GraphicsRenderer
    capabilities: CapabilityCatalog
    drawings: DrawingService


def _missing_module_reason(module: str, extra: str) -> str | None:
    try:
        available = find_spec(module) is not None
    except (ImportError, ValueError):
        available = False
    if available:
        return None
    return f"Install entari-plugin-htmlrender[{extra}] to use this backend."


def _build_backend_renderer(
    backend: GraphicsBackendName,
    settings: GraphicsSettings,
    *,
    worker: WorkerExecutor,
    observer: OperationObserver,
    operation_admission: OperationAdmissionGate,
) -> tuple[GraphicsRenderer, bool]:
    """Build one backend with its own raster-work budget."""
    budget = RasterWorkBudget(
        max_pixels=settings.max_pixels,
        max_concurrency=settings.max_concurrency,
        max_commands=settings.max_commands,
    )
    if backend == "pillow":
        reason = _missing_module_reason("PIL", "pillow")
        if reason is not None:
            return (
                _UnavailableGraphicsRenderer(backend, reason, operation_admission),
                False,
            )
        try:
            from entari_plugin_htmlrender.adapters.pillow import (  # noqa: PLC0415
                PillowRasterSceneRenderer,
            )
        except ImportError as error:
            return (
                _UnavailableGraphicsRenderer(
                    backend,
                    f"Pillow adapter import failed: {error}",
                    operation_admission,
                ),
                False,
            )
        return (
            PillowRasterSceneRenderer(
                worker=worker,
                observer=observer,
                operation_admission=operation_admission,
                budget=budget,
            ),
            True,
        )

    reason = _missing_module_reason("skia", "skia")
    if reason is not None:
        return (
            _UnavailableGraphicsRenderer(backend, reason, operation_admission),
            False,
        )
    try:
        from entari_plugin_htmlrender.adapters.skia import (  # noqa: PLC0415
            SkiaRasterSceneRenderer,
        )
    except ImportError as error:
        return (
            _UnavailableGraphicsRenderer(
                backend,
                f"Skia adapter import failed: {error}",
                operation_admission,
            ),
            False,
        )
    return (
        SkiaRasterSceneRenderer(
            worker=worker,
            observer=observer,
            operation_admission=operation_admission,
            budget=budget,
        ),
        True,
    )


def build_graphics_composition(
    settings: GraphicsSettings,
    *,
    worker: WorkerExecutor,
    observer: OperationObserver,
    operation_admission: OperationAdmissionGate,
    drawing_registry_factory: DrawingRegistryFactory | None = None,
) -> GraphicsComposition:
    """Compose independent configured backends behind one runtime gate."""
    selected = settings.backends
    if not selected and settings.backend is not None:
        selected = (settings.backend,)
    enabled: dict[GraphicsBackendName, None] = dict.fromkeys(selected)
    for drawing in settings.drawings.values():
        enabled[drawing.backend] = None
    selected = tuple(enabled)
    primary_backend = settings.backend
    if primary_backend is None and selected:
        primary_backend = selected[0]

    built: dict[GraphicsBackendName, tuple[GraphicsRenderer, bool]] = {}
    catalog = CapabilityCatalog()
    for backend in selected:
        renderer, available = _build_backend_renderer(
            backend,
            settings,
            worker=worker,
            observer=observer,
            operation_admission=operation_admission,
        )
        built[backend] = (renderer, available)
        if available:
            key = (
                PILLOW_RASTER_SCENE_RENDERER
                if backend == "pillow"
                else SKIA_RASTER_SCENE_RENDERER
            )
            catalog = catalog.with_capability(key, renderer)

    if primary_backend is None:
        primary: GraphicsRenderer = _UnavailableGraphicsRenderer(
            None,
            "Configure graphics.backend or graphics.backends before rendering "
            "raster scenes.",
            operation_admission,
        )
    else:
        primary = built[primary_backend][0]
    registry = (drawing_registry_factory or DrawingRegistry)(
        {
            name: DrawingSpec(
                backend=spec.backend,
                path=spec.path.expanduser().absolute()
                if spec.path is not None
                else None,
                module=spec.module,
                function=spec.function,
                reload=spec.reload,
            )
            for name, spec in settings.drawings.items()
        },
        worker=worker,
    )
    drawings = DrawingService(
        registry,
        {
            backend: cast("_DrawingBackend", renderer)
            for backend, (renderer, available) in built.items()
            if available
        },
        operation_admission=operation_admission,
        max_pixels=settings.max_pixels,
    )
    return GraphicsComposition(primary=primary, capabilities=catalog, drawings=drawings)


__all__ = ["GraphicsComposition", "build_graphics_composition"]
