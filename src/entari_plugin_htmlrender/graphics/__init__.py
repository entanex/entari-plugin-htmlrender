"""Backend-neutral raster-scene values and rendering contract."""

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
