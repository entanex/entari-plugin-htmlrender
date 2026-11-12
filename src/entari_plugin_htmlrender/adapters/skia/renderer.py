"""skia-python raster-scene adapter."""

# The local typed facade mirrors skia-python's public camelCase API exactly.
# ruff: noqa: N802, N803, N815

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast, final

import skia  # ty: ignore[unresolved-import] -- native extension has no Python source

from entari_plugin_htmlrender.graphics.execution import (
    draw_with_backend,
    rasterize_with_backend,
    run_drawing_callback,
)
from entari_plugin_htmlrender.graphics.models import (
    DEFAULT_RASTER_ENCODE_OPTIONS,
    RasterEncodeOptions,
)
from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
from entari_plugin_htmlrender.rendering.models import RenderOperation

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.graphics.drawing_models import (
        DrawingCanvas,
        DrawingFunction,
    )
    from entari_plugin_htmlrender.graphics.execution import RasterWorkBudget
    from entari_plugin_htmlrender.graphics.models import (
        RasterScene,
        RGBAColor,
    )
    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor


class _SkiaData(Protocol):
    def __bytes__(self) -> bytes: ...


class _SkiaImage(Protocol):
    def encodeToData(self, image_format: object, quality: int) -> _SkiaData | None: ...


class _SkiaPaint(Protocol):
    def setColor(self, color: int) -> None: ...

    def setBlendMode(self, blend_mode: object) -> None: ...


class _SkiaCanvas(Protocol):
    def clear(self, color: int) -> None: ...

    def drawColor(self, color: int, mode: object) -> None: ...

    def drawPaint(self, paint: _SkiaPaint) -> None: ...

    def drawLine(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        paint: _SkiaPaint,
    ) -> None: ...

    def drawRect(self, rect: object, paint: _SkiaPaint) -> None: ...

    def drawRoundRect(
        self,
        rect: object,
        rx: float,
        ry: float,
        paint: _SkiaPaint,
    ) -> None: ...

    def drawCircle(
        self,
        cx: float,
        cy: float,
        radius: float,
        paint: _SkiaPaint,
    ) -> None: ...

    def drawPath(self, path: object, paint: _SkiaPaint) -> None: ...

    def drawTextBlob(
        self,
        blob: object,
        x: float,
        y: float,
        paint: _SkiaPaint,
    ) -> None: ...

    def drawImage(
        self,
        image: _SkiaImage,
        x: float,
        y: float,
        sampling: object,
        paint: _SkiaPaint,
    ) -> None: ...


class _SkiaSurface(Protocol):
    def getCanvas(self) -> _SkiaCanvas: ...

    def makeImageSnapshot(self) -> _SkiaImage: ...


class _Factory(Protocol):
    def __call__(self, *args: object, **kwargs: object) -> object: ...


class _PaintFactory(Protocol):
    def __call__(
        self,
        *,
        AntiAlias: bool = False,
    ) -> _SkiaPaint: ...


class _ImageInfoFactory(Protocol):
    def Make(
        self,
        width: int,
        height: int,
        color_type: object,
        alpha_type: object,
        color_space: object,
    ) -> object: ...


class _SurfaceFactory(Protocol):
    def MakeRaster(self, info: object) -> _SkiaSurface | None: ...


class _RectFactory(Protocol):
    def MakeXYWH(self, x: int, y: int, width: int, height: int) -> object: ...


class _ColorSpaceFactory(Protocol):
    def MakeSRGB(self) -> object: ...


class _ColorTypeValues(Protocol):
    kRGBA_8888_ColorType: object


class _AlphaTypeValues(Protocol):
    kPremul_AlphaType: object


class _BlendModeValues(Protocol):
    kSrcOver: object


class _EncodedImageFormatValues(Protocol):
    kPNG: object
    kJPEG: object


class _SkiaModule(Protocol):
    ImageInfo: _ImageInfoFactory
    Surface: _SurfaceFactory
    Rect: _RectFactory
    ColorSpace: _ColorSpaceFactory
    Paint: _PaintFactory
    SamplingOptions: _Factory
    ColorType: _ColorTypeValues
    AlphaType: _AlphaTypeValues
    BlendMode: _BlendModeValues
    EncodedImageFormat: _EncodedImageFormatValues

    def ColorSetARGB(self, alpha: int, red: int, green: int, blue: int) -> int: ...


_skia = cast("_SkiaModule", skia)


@dataclass(frozen=True, slots=True)
class SkiaCanvas:
    """Skia native canvas and surface handles for one synchronous callback."""

    canvas: skia.Canvas
    surface: skia.Surface
    width: int
    height: int


def _skia_color(color: RGBAColor) -> int:
    return _skia.ColorSetARGB(color.alpha, color.red, color.green, color.blue)


def _surface(width: int, height: int) -> _SkiaSurface:
    info = _skia.ImageInfo.Make(
        width,
        height,
        _skia.ColorType.kRGBA_8888_ColorType,
        _skia.AlphaType.kPremul_AlphaType,
        _skia.ColorSpace.MakeSRGB(),
    )
    surface = _skia.Surface.MakeRaster(info)
    if surface is None:
        raise RuntimeError("Skia could not allocate an RGBA raster surface.")
    return surface


def _encode(image: _SkiaImage, output: RasterEncodeOptions) -> bytes:
    if output.format == "png":
        data = image.encodeToData(_skia.EncodedImageFormat.kPNG, 100)
    else:
        data = image.encodeToData(
            _skia.EncodedImageFormat.kJPEG,
            output.jpeg_quality,
        )
    if data is None:
        raise RuntimeError(f"Skia could not encode {output.format.upper()}.")
    return bytes(data)


def _encode_image(
    image: _SkiaImage,
    output: RasterEncodeOptions,
) -> RenderedImage:
    return RenderedImage.from_bytes(
        _encode(image, output),
        expected_format=output.format,
    )


def _rasterize_sync(
    scene: RasterScene,
    output: RasterEncodeOptions,
) -> RenderedImage:
    surface = _surface(scene.width, scene.height)
    canvas = surface.getCanvas()
    canvas.clear(_skia_color(scene.background))

    for command in scene.commands:
        rect = command.rect.clipped_to(scene.width, scene.height)
        if rect is None:
            continue
        paint = _skia.Paint(AntiAlias=False)
        paint.setColor(_skia_color(command.color))
        paint.setBlendMode(_skia.BlendMode.kSrcOver)
        canvas.drawRect(
            _skia.Rect.MakeXYWH(rect.x, rect.y, rect.width, rect.height),
            paint,
        )

    image = surface.makeImageSnapshot()
    if output.format == "jpeg":
        matte_surface = _surface(scene.width, scene.height)
        matte_canvas = matte_surface.getCanvas()
        matte_canvas.clear(_skia_color(output.jpeg_matte))
        matte_paint = _skia.Paint(AntiAlias=False)
        matte_paint.setBlendMode(_skia.BlendMode.kSrcOver)
        matte_canvas.drawImage(
            image,
            0,
            0,
            _skia.SamplingOptions(),
            matte_paint,
        )
        image = matte_surface.makeImageSnapshot()

    return _encode_image(image, output)


def _draw_sync(
    callback: DrawingFunction,
    data: Mapping[str, object],
    drawing: DrawingCanvas,
    output: RasterEncodeOptions,
) -> RenderedImage:
    surface = _surface(drawing.width, drawing.height)
    canvas = surface.getCanvas()
    canvas.clear(_skia_color(drawing.background))
    context = SkiaCanvas(
        canvas=cast("skia.Canvas", canvas),
        surface=cast("skia.Surface", surface),
        width=drawing.width,
        height=drawing.height,
    )
    run_drawing_callback("skia", callback, context, data)

    image = surface.makeImageSnapshot()
    if output.format == "jpeg":
        matte_surface = _surface(drawing.width, drawing.height)
        matte_canvas = matte_surface.getCanvas()
        matte_canvas.clear(_skia_color(output.jpeg_matte))
        matte_paint = _skia.Paint(AntiAlias=False)
        matte_paint.setBlendMode(_skia.BlendMode.kSrcOver)
        matte_canvas.drawImage(
            image,
            0,
            0,
            _skia.SamplingOptions(),
            matte_paint,
        )
        image = matte_surface.makeImageSnapshot()
    return _encode_image(image, output)


@final
class SkiaRasterSceneRenderer:
    """Rasterize neutral scenes through skia-python on an injected worker thread."""

    def __init__(
        self,
        *,
        worker: WorkerExecutor,
        observer: OperationObserver,
        operation_admission: OperationAdmissionGate,
        budget: RasterWorkBudget,
    ) -> None:
        self._worker = worker
        self._observer = observer
        self._operation_admission = operation_admission
        self._budget = budget

    async def rasterize(
        self,
        scene: RasterScene,
        *,
        output: RasterEncodeOptions = DEFAULT_RASTER_ENCODE_OPTIONS,
    ) -> RenderedImage:
        return await rasterize_with_backend(
            "skia",
            scene,
            output,
            _rasterize_sync,
            worker=self._worker,
            observer=self._observer,
            operation_admission=self._operation_admission,
            budget=self._budget,
        )

    async def draw(
        self,
        callback: DrawingFunction,
        data: Mapping[str, object],
        *,
        canvas: DrawingCanvas,
        output: RasterEncodeOptions = DEFAULT_RASTER_ENCODE_OPTIONS,
    ) -> RenderedImage:
        async with self._operation_admission.operation(
            RenderOperation.DRAWING_TO_IMAGE.value
        ):
            return await self._draw_admitted(
                callback,
                data,
                canvas=canvas,
                output=output,
            )

    async def _draw_admitted(
        self,
        callback: DrawingFunction,
        data: Mapping[str, object],
        *,
        canvas: DrawingCanvas,
        output: RasterEncodeOptions = DEFAULT_RASTER_ENCODE_OPTIONS,
    ) -> RenderedImage:
        return await draw_with_backend(
            "skia",
            callback,
            data,
            canvas,
            output,
            _draw_sync,
            worker=self._worker,
            observer=self._observer,
            budget=self._budget,
        )


__all__ = ["SkiaCanvas", "SkiaRasterSceneRenderer"]
