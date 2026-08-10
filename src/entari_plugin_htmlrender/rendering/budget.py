"""Composition-owned admission budget for neutral HTML raster work."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, final

import anyio

from entari_plugin_htmlrender.errors import (
    HtmlRenderError,
    InvalidRenderInputError,
    ProviderExecutionError,
    RenderOutputLimitError,
)
from entari_plugin_htmlrender.rendering.models import RenderOperation

if TYPE_CHECKING:
    from entari_plugin_htmlrender.preparation.models import (
        PreparedHtml,
        RasterOptions,
    )
    from entari_plugin_htmlrender.resources.config import (
        ResourceMaterializationPolicy,
    )

    from .artifacts import RenderedImage
    from .ports import PreparedHtmlExecutor


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def _prepared_source_size(prepared: PreparedHtml, limit: int) -> int:
    total = _utf8_size(prepared.html)
    if total > limit:
        return total
    for stylesheet in prepared.stylesheets:
        total += _utf8_size(stylesheet.css)
        if total > limit:
            return total
    for asset in prepared.assets:
        total += len(asset.data)
        if total > limit:
            return total
    return total


def _device_dimension(value: int, ratio: float) -> int:
    return math.ceil(value * ratio)


_SOURCE_FIELDS: dict[RenderOperation, str] = {
    RenderOperation.HTML_TO_IMAGE: "html",
    RenderOperation.TEXT_TO_IMAGE: "text",
    RenderOperation.MARKDOWN_TO_IMAGE: "source",
    RenderOperation.TEMPLATE_TO_IMAGE: "template",
    RenderOperation.PREPARED_HTML_TO_IMAGE: "prepared",
}


def _source_field(operation: RenderOperation) -> str:
    try:
        return _SOURCE_FIELDS[operation]
    except KeyError:
        raise ValueError(
            f"Operation {operation.value!r} does not execute prepared HTML."
        ) from None


@final
class HtmlRenderBudget:
    """Bound prepared input, physical output, scale, and shared concurrency."""

    def __init__(
        self,
        *,
        max_source_bytes: int = 64 * 1024 * 1024,
        max_pixels: int = 16 * 1024 * 1024,
        max_output_bytes: int = 64 * 1024 * 1024,
        max_device_pixel_ratio: float = 4.0,
        max_auto_height: int = 16_384,
        max_concurrency: int = 2,
    ) -> None:
        if max_source_bytes <= 0:
            raise ValueError("max_source_bytes must be positive")
        if max_pixels <= 0:
            raise ValueError("max_pixels must be positive")
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        if not math.isfinite(max_device_pixel_ratio) or max_device_pixel_ratio <= 0:
            raise ValueError("max_device_pixel_ratio must be finite and positive")
        if max_auto_height <= 0:
            raise ValueError("max_auto_height must be positive")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        self._max_source_bytes = max_source_bytes
        self._max_pixels = max_pixels
        self._max_output_bytes = max_output_bytes
        self._max_device_pixel_ratio = max_device_pixel_ratio
        self._max_auto_height = max_auto_height
        self._max_concurrency = max_concurrency
        self._slots = anyio.Semaphore(max_concurrency)

    @property
    def max_source_bytes(self) -> int:
        return self._max_source_bytes

    @property
    def max_pixels(self) -> int:
        return self._max_pixels

    @property
    def max_output_bytes(self) -> int:
        return self._max_output_bytes

    @property
    def max_device_pixel_ratio(self) -> float:
        return self._max_device_pixel_ratio

    @property
    def max_auto_height(self) -> int:
        return self._max_auto_height

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    def validate_request(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        operation: RenderOperation,
    ) -> None:
        field = _source_field(operation)
        source_bytes = _prepared_source_size(prepared, self._max_source_bytes)
        if source_bytes > self._max_source_bytes:
            raise InvalidRenderInputError(
                f"Prepared HTML contains {source_bytes} source bytes, exceeding "
                f"the configured limit of {self._max_source_bytes}.",
                operation=operation.value,
                field=field,
            )
        if options.device_pixel_ratio > self._max_device_pixel_ratio:
            raise InvalidRenderInputError(
                "Raster device_pixel_ratio "
                f"{options.device_pixel_ratio:g} exceeds the configured limit "
                f"of {self._max_device_pixel_ratio:g}.",
                operation=operation.value,
                field="raster.device_pixel_ratio",
            )
        if options.height is None:
            return
        width = _device_dimension(options.width, options.device_pixel_ratio)
        height = _device_dimension(options.height, options.device_pixel_ratio)
        pixels = width * height
        if pixels > self._max_pixels:
            raise InvalidRenderInputError(
                f"Raster request contains {pixels} physical pixels, exceeding "
                f"the configured limit of {self._max_pixels}.",
                operation=operation.value,
                field="raster.dimensions",
            )

    def validate_result(
        self,
        result: RenderedImage,
        options: RasterOptions,
        *,
        operation: RenderOperation,
    ) -> None:
        output_bytes = len(result.data)
        if output_bytes > self._max_output_bytes:
            raise RenderOutputLimitError(
                operation.value,
                "bytes",
                actual=output_bytes,
                maximum=self._max_output_bytes,
            )
        pixels = result.width * result.height
        if pixels > self._max_pixels:
            raise RenderOutputLimitError(
                operation.value,
                "pixels",
                actual=pixels,
                maximum=self._max_pixels,
            )
        if options.height is None:
            max_device_height = _device_dimension(
                self._max_auto_height,
                options.device_pixel_ratio,
            )
            if result.height > max_device_height:
                raise RenderOutputLimitError(
                    operation.value,
                    "auto_height",
                    actual=result.height,
                    maximum=max_device_height,
                )

    async def acquire(self) -> None:
        """Reserve one shared HTML-render slot."""
        await self._slots.acquire()

    def release(self) -> None:
        """Release one previously reserved HTML-render slot."""
        self._slots.release()


@final
class BudgetedPreparedHtmlExecutor:
    """Apply one shared budget around any provider's neutral executor."""

    def __init__(
        self,
        executor: PreparedHtmlExecutor,
        budget: HtmlRenderBudget,
        *,
        provider_id: str,
    ) -> None:
        self._executor = executor
        self._budget = budget
        self._provider_id = provider_id

    async def execute(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        operation: RenderOperation,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> RenderedImage:
        self._budget.validate_request(
            prepared,
            options,
            operation=operation,
        )
        await self._budget.acquire()
        try:
            try:
                result = await self._executor.execute(
                    prepared,
                    options,
                    operation=operation,
                    materialization_policy=materialization_policy,
                )
                self._budget.validate_result(
                    result,
                    options,
                    operation=operation,
                )
                return result
            except ProviderExecutionError as error:
                if (
                    error.provider_id == self._provider_id
                    and error.operation == operation.value
                ):
                    raise
                raise ProviderExecutionError(
                    "The selected provider failed while rendering prepared HTML.",
                    provider_id=self._provider_id,
                    operation=operation.value,
                    retryable=error.retryable,
                    source=error,
                ) from error
            except HtmlRenderError:
                raise
            except Exception as error:
                raise ProviderExecutionError(
                    "The selected provider failed while rendering prepared HTML.",
                    provider_id=self._provider_id,
                    operation=operation.value,
                    source=error,
                ) from error
        finally:
            self._budget.release()


__all__ = ["BudgetedPreparedHtmlExecutor", "HtmlRenderBudget"]
