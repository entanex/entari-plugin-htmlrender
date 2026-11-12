from __future__ import annotations

from contextlib import asynccontextmanager
from io import BytesIO
from typing import TYPE_CHECKING, cast

import anyio
from anyio.lowlevel import checkpoint
from PIL import Image
from pydantic import ValidationError
import pytest

from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.errors import (
    GraphicsBackendUnavailableError,
    InvalidRenderInputError,
    RuntimeUnavailableError,
)
from entari_plugin_htmlrender.graphics import RasterScene, RGBAColor
from entari_plugin_htmlrender.graphics.drawing_loader import DrawingRegistry

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from pytest_mock import MockerFixture

    from entari_plugin_htmlrender.graphics import GraphicsBackendName
    from entari_plugin_htmlrender.rendering.artifacts import RenderedImage


def _write_drawing(path: Path, backend: GraphicsBackendName, color: str) -> None:
    source = (
        "def draw(canvas, data):\n"
        f"    canvas.image.paste('{color}', (0, 0, canvas.width, canvas.height))\n"
    )
    if backend == "skia":
        source = (
            "import skia\n"
            "def draw(canvas, data):\n"
            f"    canvas.canvas.clear(skia.Color{color.upper()})\n"
        )
    path.write_text(source, encoding="utf-8")


def _config(path: Path, backend: str = "pillow", *, reload: bool = False):
    return HtmlRenderConfig.model_validate(
        {
            "graphics": {
                "drawings": {
                    "card": {
                        "path": path,
                        "backend": backend,
                        "reload": reload,
                    }
                },
                "max_pixels": 64,
                "max_concurrency": 1,
            }
        }
    )


def _pixel(image: RenderedImage):
    with Image.open(BytesIO(bytes(image))) as decoded:
        return decoded.convert("RGBA").getpixel((0, 0))


@pytest.mark.parametrize(
    "source",
    [
        {},
        {"path": "card.py", "module": "cards"},
        {"path": "card.txt"},
        {"module": ".cards"},
        {"module": "card module"},
        {"module": "cards", "function": "draw.nested"},
        {"module": "cards", "function": "class"},
        {"module": "cards", "function": "draw "},
    ],
)
def test_drawing_config_rejects_ambiguous_or_invalid_sources(source) -> None:
    with pytest.raises(ValidationError):
        HtmlRenderConfig.model_validate(
            {"graphics": {"drawings": {"card": {"backend": "pillow", **source}}}}
        )


@pytest.mark.parametrize("function", ["draw", "draw_card"])
def test_drawing_config_accepts_explicit_function_names(function: str) -> None:
    config = HtmlRenderConfig.model_validate(
        {
            "graphics": {
                "drawings": {
                    "card": {
                        "backend": "pillow",
                        "module": "cards",
                        "function": function,
                    }
                }
            }
        }
    )
    assert config.graphics.drawings["card"].function == function


@pytest.mark.parametrize("name", ["", " card", "card "])
def test_drawing_config_rejects_unusable_names(name: str) -> None:
    with pytest.raises(ValidationError):
        HtmlRenderConfig.model_validate(
            {"graphics": {"drawings": {name: {"backend": "pillow", "module": "cards"}}}}
        )


@pytest.mark.parametrize("backend", ["pillow", "skia"])
async def test_named_drawing_automatically_enables_its_backend(
    tmp_path: Path, backend: GraphicsBackendName
) -> None:
    path = tmp_path / "card.py"
    _write_drawing(path, backend, "red")
    runtime = build_runtime_plan(_config(path, backend)).build_runtime()
    try:
        assert runtime.drawings.names == frozenset({"card"})
        image = await runtime.drawings.render("card", width=4, height=3)
        assert (image.width, image.height) == (4, 3)
        assert _pixel(image) == (255, 0, 0, 255)
        scene = await runtime.graphics.rasterize(
            RasterScene(4, 3, background=RGBAColor(0, 255, 0))
        )
        assert _pixel(scene) == (0, 255, 0, 255)
    finally:
        await runtime.aclose()


async def test_named_drawings_reload_without_replacing_runtime(tmp_path: Path) -> None:
    path = tmp_path / "card.py"
    _write_drawing(path, "pillow", "red")
    runtime = build_runtime_plan(_config(path, reload=True)).build_runtime()
    drawings = runtime.drawings
    try:
        assert _pixel(await drawings.render("card", width=2, height=2)) == (
            255,
            0,
            0,
            255,
        )
        path.write_text("this is not valid Python!", encoding="utf-8")
        assert _pixel(await drawings.render("card", width=2, height=2)) == (
            255,
            0,
            0,
            255,
        )
        _write_drawing(path, "pillow", "blue")
        assert _pixel(await drawings.render("card", width=2, height=2)) == (
            0,
            0,
            255,
            255,
        )
        assert runtime.drawings is drawings
    finally:
        await runtime.aclose()


async def test_manual_reload_is_available_when_auto_reload_is_off(
    tmp_path: Path,
) -> None:
    path = tmp_path / "card.py"
    _write_drawing(path, "pillow", "red")
    runtime = build_runtime_plan(_config(path)).build_runtime()
    try:
        await runtime.drawings.render("card", width=2, height=2)
        _write_drawing(path, "pillow", "blue")
        assert _pixel(await runtime.drawings.render("card", width=2, height=2)) == (
            255,
            0,
            0,
            255,
        )
        await runtime.drawings.reload("card")
        assert _pixel(await runtime.drawings.render("card", width=2, height=2)) == (
            0,
            0,
            255,
            255,
        )
    finally:
        await runtime.aclose()


async def test_invalid_canvas_does_not_import_drawing(tmp_path: Path) -> None:
    path = tmp_path / "never_import.py"
    path.write_text("raise AssertionError('must not execute')", encoding="utf-8")
    runtime = build_runtime_plan(_config(path)).build_runtime()
    try:
        with pytest.raises(InvalidRenderInputError, match="pixels"):
            await runtime.drawings.render("card", width=9, height=9)
        with pytest.raises(InvalidRenderInputError, match="mapping"):
            await runtime.drawings.render(
                "card", cast("Mapping[str, object]", []), width=2, height=2
            )
    finally:
        await runtime.aclose()


async def test_missing_backend_does_not_import_drawing(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    mocker.patch(
        "entari_plugin_htmlrender._graphics_composition.find_spec", return_value=None
    )
    runtime = build_runtime_plan(_config(tmp_path / "missing.py")).build_runtime()
    try:
        with pytest.raises(GraphicsBackendUnavailableError):
            await runtime.drawings.render("card", width=2, height=2)
    finally:
        await runtime.aclose()


async def test_shutdown_drains_drawing_before_native_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "card.py"
    _write_drawing(path, "pillow", "red")
    runtime = build_runtime_plan(_config(path)).build_runtime()
    source_ready = anyio.Event()
    resume = anyio.Event()
    closed = anyio.Event()
    images: list[RenderedImage] = []
    original_lease = DrawingRegistry.lease

    @asynccontextmanager
    async def paused_lease(registry, name):
        async with original_lease(registry, name) as callback:
            source_ready.set()
            await resume.wait()
            yield callback

    monkeypatch.setattr(DrawingRegistry, "lease", paused_lease)

    async def render() -> None:
        images.append(await runtime.drawings.render("card", width=2, height=2))

    async def close() -> None:
        await runtime.aclose()
        closed.set()

    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(render)
            await source_ready.wait()
            group.start_soon(close)
            while runtime.state.value != "closing":
                await checkpoint()
            assert not closed.is_set()
            resume.set()
    assert _pixel(images[0]) == (255, 0, 0, 255)
    assert closed.is_set()
    with pytest.raises(RuntimeUnavailableError):
        await runtime.drawings.render("card", width=2, height=2)
    with pytest.raises(RuntimeUnavailableError):
        await runtime.drawings.reload("card")


async def test_named_drawings_use_their_own_backend(tmp_path: Path) -> None:
    pillow = tmp_path / "pillow_card.py"
    skia = tmp_path / "skia_card.py"
    _write_drawing(pillow, "pillow", "red")
    _write_drawing(skia, "skia", "blue")
    config = HtmlRenderConfig.model_validate(
        {
            "graphics": {
                "drawings": {
                    "pillow-card": {"backend": "pillow", "path": pillow},
                    "skia-card": {"backend": "skia", "path": skia},
                }
            }
        }
    )
    runtime = build_runtime_plan(config).build_runtime()
    try:
        assert runtime.drawings.names == frozenset({"pillow-card", "skia-card"})
        first = await runtime.drawings.render("pillow-card", width=2, height=2)
        second = await runtime.drawings.render("skia-card", width=2, height=2)
        assert _pixel(first) == (255, 0, 0, 255)
        assert _pixel(second) == (0, 0, 255, 255)
        assert runtime.capabilities.pillow is not runtime.capabilities.skia
    finally:
        await runtime.aclose()
