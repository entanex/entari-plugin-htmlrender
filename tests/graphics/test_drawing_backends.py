from __future__ import annotations

import gc
from io import BytesIO
import time
from typing import TYPE_CHECKING, cast
import warnings

import anyio
from anyio import from_thread, lowlevel, wait_all_tasks_blocked
from PIL import Image, ImageDraw, ImageFont
import pytest
import skia  # ty: ignore[unresolved-import] -- native extension has no Python source

from entari_plugin_htmlrender.adapters.pillow import (
    PillowCanvas,
    PillowRasterSceneRenderer,
)
from entari_plugin_htmlrender.adapters.resources import AnyioWorkerExecutor
from entari_plugin_htmlrender.adapters.skia import (
    SkiaCanvas,
    SkiaRasterSceneRenderer,
)
from entari_plugin_htmlrender.errors import (
    GraphicsError,
    InvalidRenderInputError,
    RuntimeUnavailableError,
)
from entari_plugin_htmlrender.graphics.drawing_models import (
    DrawingCanvas,
    DrawingFunction,
)
from entari_plugin_htmlrender.graphics.errors import (
    DrawingBackendExecutionError,
    RasterBackendExecutionError,
)
from entari_plugin_htmlrender.graphics.execution import RasterWorkBudget
from entari_plugin_htmlrender.graphics.models import (
    RasterEncodeOptions,
    RasterScene,
    RGBAColor,
)
from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
from entari_plugin_htmlrender.rendering.observers import NoopOperationObserver
from tests.adapters.conftest import RecordingOperationObserver

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor


Renderer = PillowRasterSceneRenderer | SkiaRasterSceneRenderer
RendererType = type[PillowRasterSceneRenderer] | type[SkiaRasterSceneRenderer]


def unsafe_callback(callback: object) -> DrawingFunction:
    """Narrow test callbacks whose adapter-specific context is checked at runtime."""
    return cast("DrawingFunction", callback)


def _renderer(
    renderer_type: RendererType,
    *,
    observer: OperationObserver | None = None,
    worker: WorkerExecutor | None = None,
    admission: OperationAdmissionGate | None = None,
    max_pixels: int = 1_000_000,
    max_concurrency: int = 2,
    max_commands: int = 100_000,
) -> Renderer:
    return renderer_type(
        worker=worker or AnyioWorkerExecutor(),
        observer=observer or NoopOperationObserver(),
        operation_admission=admission or OperationAdmissionGate(),
        budget=RasterWorkBudget(
            max_pixels=max_pixels,
            max_concurrency=max_concurrency,
            max_commands=max_commands,
        ),
    )


def _decoded(image: RenderedImage) -> Image.Image:
    return Image.open(BytesIO(image.data))


def _pixel(
    image: RenderedImage,
    x: int,
    y: int,
    *,
    mode: str,
) -> tuple[int, ...]:
    with _decoded(image) as decoded:
        value = decoded.convert(mode).getpixel((x, y))
    assert isinstance(value, tuple)
    return value


def _channels_close(
    actual: tuple[int, ...],
    expected: tuple[int, ...],
    *,
    tolerance: int,
) -> bool:
    return len(actual) == len(expected) and all(
        abs(left - right) <= tolerance
        for left, right in zip(actual, expected, strict=True)
    )


def _draw_pillow(
    canvas: PillowCanvas,
    data: Mapping[str, object],
) -> None:
    label = str(data["label"])
    font = ImageFont.load_default(size=20)
    canvas.draw.ellipse(
        (2, 2, 28, 28),
        fill=(20, 180, 80, 160),
    )
    canvas.draw.line((0, 38, 79, 8), fill=(255, 255, 255, 255), width=3)
    canvas.draw.text((36, 8), label, font=font, fill=(255, 250, 40, 255))


def _draw_skia(canvas: SkiaCanvas, data: Mapping[str, object]) -> None:
    label = str(data["label"])
    paint = skia.Paint(AntiAlias=False)
    paint.setColor(skia.ColorBLUE)
    canvas.canvas.drawRect(
        skia.Rect.MakeXYWH(2, 2, 20, 16),
        paint,
    )

    path = skia.Path()
    path.moveTo(28, 2)
    path.lineTo(50, 2)
    path.lineTo(28, 22)
    path.close()
    paint.setColor(skia.ColorGREEN)
    canvas.canvas.drawPath(path, paint)

    paint.setColor(skia.ColorRED)
    canvas.canvas.drawCircle(65, 12, 8, paint)
    font = skia.Font(skia.Typeface.MakeFromName("Arial"), 16)
    canvas.canvas.drawTextBlob(
        skia.TextBlob.MakeFromString(label, font),
        4,
        36,
        paint,
    )


@pytest.mark.parametrize(
    ("renderer_type", "draw"),
    [
        pytest.param(PillowRasterSceneRenderer, _draw_pillow, id="pillow"),
        pytest.param(SkiaRasterSceneRenderer, _draw_skia, id="skia"),
    ],
)
async def test_native_drawing_renders_real_content_and_png_dimensions(
    renderer_type: RendererType,
    draw: DrawingFunction,
) -> None:
    operation_observer = RecordingOperationObserver()
    result = await _renderer(
        renderer_type,
        observer=operation_observer,
    ).draw(
        draw,
        {"label": "Hi"},
        canvas=DrawingCanvas(80, 40, RGBAColor(8, 16, 24, 255)),
    )

    assert (result.format, result.width, result.height) == ("png", 80, 40)
    with _decoded(result) as decoded:
        assert decoded.mode == "RGBA"
        assert decoded.getbbox() == (0, 0, 80, 40)
        assert decoded.getcolors(maxcolors=80 * 40) is not None
        assert len(decoded.getcolors(maxcolors=80 * 40) or ()) > 3
        pixel = decoded.getpixel((40, 20))
        assert isinstance(pixel, tuple)
        assert pixel[3] == 255
    assert operation_observer.operations == [
        (
            f"graphics.{'pillow' if renderer_type is PillowRasterSceneRenderer else 'skia'}"
            ".draw",
            {
                "render.backend": (
                    "pillow" if renderer_type is PillowRasterSceneRenderer else "skia"
                ),
                "render.format": "png",
            },
            "success",
        )
    ]


@pytest.mark.parametrize(
    ("renderer_type", "draw"),
    [
        pytest.param(PillowRasterSceneRenderer, _draw_pillow, id="pillow"),
        pytest.param(SkiaRasterSceneRenderer, _draw_skia, id="skia"),
    ],
)
async def test_native_drawing_encodes_jpeg_over_the_requested_matte(
    renderer_type: RendererType,
    draw: DrawingFunction,
) -> None:
    result = await _renderer(renderer_type).draw(
        draw,
        {"label": "Hi"},
        canvas=DrawingCanvas(80, 40),
        output=RasterEncodeOptions(
            format="jpeg",
            quality=100,
            matte=RGBAColor(12, 55, 170),
        ),
    )

    assert (result.format, result.width, result.height) == ("jpeg", 80, 40)
    assert _channels_close(
        _pixel(result, 0, 20, mode="RGB"),
        (12, 55, 170),
        tolerance=3,
    )


@pytest.mark.parametrize(
    ("renderer_type", "draw"),
    [
        pytest.param(PillowRasterSceneRenderer, _draw_pillow, id="pillow"),
        pytest.param(SkiaRasterSceneRenderer, _draw_skia, id="skia"),
    ],
)
async def test_native_drawing_creates_a_fresh_context_per_call(
    renderer_type: RendererType,
    draw: DrawingFunction,
) -> None:
    renderer = _renderer(renderer_type)
    contexts: list[object] = []

    def capture(context: object, data: Mapping[str, object]) -> None:
        del data
        contexts.append(context)
        if isinstance(context, PillowCanvas):
            context.draw.rectangle(
                (0, 0, context.width - 1, context.height - 1),
                fill=(255, 0, 0, 255),
            )
        else:
            assert isinstance(context, SkiaCanvas)
            paint = skia.Paint(AntiAlias=False)
            paint.setColor(skia.ColorRED)
            context.canvas.drawPaint(paint)

    first = await renderer.draw(
        capture,
        {},
        canvas=DrawingCanvas(5, 4),
    )
    second = await renderer.draw(
        draw,
        {"label": "Hi"},
        canvas=DrawingCanvas(8, 6),
    )

    assert len(contexts) == 1
    assert (first.width, first.height) == (5, 4)
    assert (second.width, second.height) == (8, 6)
    assert _pixel(first, 2, 2, mode="RGBA") == (255, 0, 0, 255)
    assert _pixel(second, 0, 0, mode="RGBA") == (0, 0, 0, 0)


async def test_pillow_callback_cannot_resize_the_configured_canvas() -> None:
    def resize(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
        del data
        canvas.image.thumbnail((2, 2))

    with pytest.raises(
        DrawingBackendExecutionError,
        match=r"changed the canvas from 8x6 to 2x2",
    ) as raised:
        await _renderer(PillowRasterSceneRenderer).draw(
            unsafe_callback(resize),
            {},
            canvas=DrawingCanvas(8, 6),
        )

    assert raised.value.operation == "drawing_to_image"
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    "renderer_type",
    [
        pytest.param(PillowRasterSceneRenderer, id="pillow"),
        pytest.param(SkiaRasterSceneRenderer, id="skia"),
    ],
)
async def test_callback_return_contract_is_an_input_error(
    renderer_type: RendererType,
) -> None:
    def invalid(canvas: object, data: Mapping[str, object]) -> object:
        del canvas, data
        return object()

    with pytest.raises(InvalidRenderInputError) as raised:
        await _renderer(renderer_type).draw(
            unsafe_callback(invalid),
            {},
            canvas=DrawingCanvas(4, 4),
        )

    assert raised.value.operation == "drawing_to_image"
    assert raised.value.field == "callback.return"


@pytest.mark.parametrize(
    "renderer_type",
    [
        pytest.param(PillowRasterSceneRenderer, id="pillow"),
        pytest.param(SkiaRasterSceneRenderer, id="skia"),
    ],
)
async def test_async_callback_coroutine_is_closed_without_a_warning(
    renderer_type: RendererType,
) -> None:
    coroutine_closed = False

    async def asynchronous(canvas: object, data: Mapping[str, object]) -> None:
        nonlocal coroutine_closed
        del canvas, data
        try:
            await lowlevel.checkpoint()
        finally:
            coroutine_closed = True

    def invalid(canvas: object, data: Mapping[str, object]) -> object:
        return asynchronous(canvas, data)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(InvalidRenderInputError, match="must return None"):
            await _renderer(renderer_type).draw(
                unsafe_callback(invalid),
                {},
                canvas=DrawingCanvas(4, 4),
            )
        gc.collect()

    assert coroutine_closed is False
    assert not [
        warning for warning in caught if "was never awaited" in str(warning.message)
    ]


@pytest.mark.parametrize(
    "renderer_type",
    [
        pytest.param(PillowRasterSceneRenderer, id="pillow"),
        pytest.param(SkiaRasterSceneRenderer, id="skia"),
    ],
)
async def test_native_callback_failure_preserves_the_original_cause(
    renderer_type: RendererType,
) -> None:
    source = LookupError("callback sentinel")

    def fail(canvas: object, data: Mapping[str, object]) -> None:
        del canvas, data
        raise source

    with pytest.raises(DrawingBackendExecutionError) as raised:
        await _renderer(renderer_type).draw(
            fail,
            {},
            canvas=DrawingCanvas(4, 4),
        )

    assert raised.value.operation == "drawing_to_image"
    assert isinstance(raised.value, GraphicsError)
    assert raised.value.__cause__ is source


async def test_drawing_rejects_oversized_canvas_before_worker_or_surface() -> None:
    worker_called = False

    class RecordingWorker:
        async def run_sync(self, function, /, *args, **kwargs):
            nonlocal worker_called
            del function, args, kwargs
            worker_called = True
            raise AssertionError("oversized drawing reached the worker")

    def no_draw(canvas: object, data: Mapping[str, object]) -> None:
        del canvas, data

    with pytest.raises(InvalidRenderInputError, match="pixels") as raised:
        await _renderer(
            SkiaRasterSceneRenderer,
            worker=RecordingWorker(),
            max_pixels=15,
        ).draw(
            no_draw,
            {},
            canvas=DrawingCanvas(4, 4),
        )

    assert raised.value.operation == "drawing_to_image"
    assert raised.value.field == "canvas"
    assert worker_called is False


async def test_native_draw_call_count_is_not_limited_by_max_commands() -> None:
    draws = 0

    def many_rectangles(
        canvas: PillowCanvas,
        data: Mapping[str, object],
    ) -> None:
        nonlocal draws
        del data
        for index in range(12):
            canvas.draw.rectangle(
                (index, index, index + 2, index + 2),
                fill=(index * 10, 0, 0, 255),
            )
            draws += 1

    result = await _renderer(
        PillowRasterSceneRenderer,
        max_commands=1,
    ).draw(
        unsafe_callback(many_rectangles),
        {},
        canvas=DrawingCanvas(20, 20),
    )

    assert draws == 12
    assert (result.width, result.height) == (20, 20)


async def test_drawing_and_scene_use_the_same_backend_semaphore() -> None:
    renderer = _renderer(
        PillowRasterSceneRenderer,
        max_concurrency=1,
    )
    drawing_entered = anyio.Event()
    release_drawing = anyio.Event()
    scene_entered = anyio.Event()

    def blocked_drawing(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
        del data
        from_thread.run_sync(drawing_entered.set)
        while not release_drawing.is_set():
            time.sleep(0.001)
        canvas.draw.rectangle((0, 0, 1, 1), fill=(255, 0, 0, 255))

    async def render_drawing() -> None:
        await renderer.draw(
            unsafe_callback(blocked_drawing),
            {},
            canvas=DrawingCanvas(2, 2),
        )

    async def render_scene() -> None:
        await renderer.rasterize(RasterScene(2, 2))
        scene_entered.set()

    async with anyio.create_task_group() as group:
        group.start_soon(render_drawing)
        await drawing_entered.wait()
        group.start_soon(render_scene)
        await wait_all_tasks_blocked()
        assert not scene_entered.is_set()
        release_drawing.set()

    assert scene_entered.is_set()


async def test_public_draw_gate_drains_callback_and_private_method_skips_gate() -> None:
    gate = OperationAdmissionGate()
    renderer = _renderer(
        PillowRasterSceneRenderer,
        admission=gate,
    )
    callback_entered = anyio.Event()
    release_callback = anyio.Event()
    closed = anyio.Event()
    images: list[RenderedImage] = []

    def blocked(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
        del data
        canvas.draw.rectangle((0, 0, 0, 0), fill=(255, 255, 255, 255))
        from_thread.run_sync(callback_entered.set)
        while not release_callback.is_set():
            time.sleep(0.001)

    def immediate(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
        del canvas, data

    async def public_draw() -> None:
        images.append(
            await renderer.draw(
                unsafe_callback(blocked),
                {},
                canvas=DrawingCanvas(2, 2),
            )
        )

    async def close() -> None:
        await gate.stop_accepting_and_drain()
        await gate.mark_closed()
        closed.set()

    async with anyio.create_task_group() as group:
        group.start_soon(public_draw)
        await callback_entered.wait()
        group.start_soon(close)
        await wait_all_tasks_blocked()
        assert not closed.is_set()
        release_callback.set()

    assert closed.is_set()
    assert _pixel(images[0], 0, 0, mode="RGBA") == (255, 255, 255, 255)
    with pytest.raises(RuntimeUnavailableError):
        await renderer.draw(
            unsafe_callback(immediate),
            {},
            canvas=DrawingCanvas(1, 1),
        )

    admitted = await renderer._draw_admitted(
        unsafe_callback(immediate),
        {},
        canvas=DrawingCanvas(3, 2),
    )
    assert (admitted.width, admitted.height) == (3, 2)


def test_public_canvas_contexts_expose_the_native_handles() -> None:
    with Image.new("RGBA", (3, 2)) as image:
        draw = ImageDraw.Draw(image)
        pillow = PillowCanvas(image, draw, 3, 2)
        assert isinstance(pillow.image, Image.Image)
        assert isinstance(pillow.draw, ImageDraw.ImageDraw)

    info = skia.ImageInfo.Make(
        3,
        2,
        skia.ColorType.kRGBA_8888_ColorType,
        skia.AlphaType.kPremul_AlphaType,
        skia.ColorSpace.MakeSRGB(),
    )
    surface = skia.Surface.MakeRaster(info)
    assert surface is not None
    canvas = surface.getCanvas()
    skia_context = SkiaCanvas(canvas, surface, 3, 2)
    assert isinstance(skia_context.canvas, skia.Canvas)
    assert isinstance(skia_context.surface, skia.Surface)


def test_scene_execution_error_identity_is_unchanged() -> None:
    error = RasterBackendExecutionError("pillow", "failed")
    assert error.operation == "raster_scene_to_image"


def test_drawing_execution_error_has_its_own_stable_identity() -> None:
    error = DrawingBackendExecutionError("skia", "failed")
    assert error.operation == "drawing_to_image"


def test_drawing_canvas_rejects_non_strict_dimensions() -> None:
    for kwargs in (
        {"width": True, "height": 1},
        {"width": 1.0, "height": 1},
        {"width": 1, "height": 0},
    ):
        with pytest.raises(InvalidRenderInputError) as raised:
            DrawingCanvas(
                width=cast("int", kwargs["width"]),
                height=cast("int", kwargs["height"]),
            )
        assert raised.value.operation == "drawing_to_image"
