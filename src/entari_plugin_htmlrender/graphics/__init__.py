"""Backend-neutral raster-scene values and rendering contract."""

from .capabilities import (
    PILLOW_RASTER_SCENE_RENDERER as PILLOW_RASTER_SCENE_RENDERER,
)
from .capabilities import (
    SKIA_RASTER_SCENE_RENDERER as SKIA_RASTER_SCENE_RENDERER,
)
from .drawing_loader import DrawingLoadError as DrawingLoadError
from .drawing_loader import DrawingNotFoundError as DrawingNotFoundError
from .drawing_models import DrawingCanvas as DrawingCanvas
from .drawings import DrawingRenderer as DrawingRenderer
from .errors import DrawingBackendExecutionError as DrawingBackendExecutionError
from .errors import (
    GraphicsBackendUnavailableError as GraphicsBackendUnavailableError,
)
from .errors import GraphicsError as GraphicsError
from .errors import RasterBackendExecutionError as RasterBackendExecutionError
from .models import FillRect as FillRect
from .models import GraphicsBackendName as GraphicsBackendName
from .models import PixelRect as PixelRect
from .models import RasterEncodeOptions as RasterEncodeOptions
from .models import RasterScene as RasterScene
from .models import RGBAColor as RGBAColor
from .ports import GraphicsRenderer as GraphicsRenderer

__all__ = [
    "PILLOW_RASTER_SCENE_RENDERER",
    "SKIA_RASTER_SCENE_RENDERER",
    "DrawingBackendExecutionError",
    "DrawingCanvas",
    "DrawingLoadError",
    "DrawingNotFoundError",
    "DrawingRenderer",
    "FillRect",
    "GraphicsBackendName",
    "GraphicsBackendUnavailableError",
    "GraphicsError",
    "GraphicsRenderer",
    "PixelRect",
    "RGBAColor",
    "RasterBackendExecutionError",
    "RasterEncodeOptions",
    "RasterScene",
]
