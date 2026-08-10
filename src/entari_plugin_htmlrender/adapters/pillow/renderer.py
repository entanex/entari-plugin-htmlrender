"""Pillow raster-scene adapter."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, final

from PIL import Image

from entari_plugin_htmlrender.graphics.execution import rasterize_with_backend
from entari_plugin_htmlrender.graphics.models import (
    DEFAULT_RASTER_ENCODE_OPTIONS,
    RasterEncodeOptions,
)
from entari_plugin_htmlrender.rendering.artifacts import RenderedImage

if TYPE_CHECKING:
    from entari_plugin_htmlrender.graphics.execution import RasterWorkBudget
    from entari_plugin_htmlrender.graphics.models import RasterScene
    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor


def _rasterize_sync(
    scene: RasterScene,
    output: RasterEncodeOptions,
) -> RenderedImage:
    with Image.new(
        "RGBA",
        (scene.width, scene.height),
        scene.background.as_tuple(),
    ) as image:
        for command in scene.commands:
            rect = command.rect.clipped_to(scene.width, scene.height)
            if rect is None:
                continue
            with Image.new(
                "RGBA",
                (rect.width, rect.height),
                command.color.as_tuple(),
            ) as source:
                image.alpha_composite(source, dest=(rect.x, rect.y))

        stream = BytesIO()
        if output.format == "png":
            image.save(stream, format="PNG")
        else:
            with Image.new(
                "RGBA",
                image.size,
                output.jpeg_matte.as_tuple(),
            ) as matte:
                matte.alpha_composite(image)
                with matte.convert("RGB") as opaque:
                    opaque.save(
                        stream,
                        format="JPEG",
                        quality=output.jpeg_quality,
                    )
        return RenderedImage.from_bytes(
            stream.getvalue(),
            expected_format=output.format,
        )


@final
class PillowRasterSceneRenderer:
    """Rasterize neutral scenes through Pillow on an injected worker thread."""

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
            "pillow",
            scene,
            output,
            _rasterize_sync,
            worker=self._worker,
            observer=self._observer,
            operation_admission=self._operation_admission,
            budget=self._budget,
        )


__all__ = ["PillowRasterSceneRenderer"]
