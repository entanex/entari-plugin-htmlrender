from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest

from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    ProviderExecutionError,
    RenderOutputLimitError,
)
from entari_plugin_htmlrender.preparation import (
    PreparedAsset,
    RasterOptions,
    parse_html,
)
from entari_plugin_htmlrender.rendering.budget import (
    BudgetedPreparedHtmlExecutor,
    HtmlRenderBudget,
)
from entari_plugin_htmlrender.rendering.models import RenderOperation
from tests.image_fixtures import rendered_image

if TYPE_CHECKING:
    from entari_plugin_htmlrender.preparation.models import PreparedHtml
    from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
    from entari_plugin_htmlrender.resources.config import (
        ResourceMaterializationPolicy,
    )


class _Executor:
    def __init__(self, result: RenderedImage) -> None:
        self.result = result
        self.failure: Exception | None = None
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self._lock = anyio.Lock()

    async def execute(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        operation: RenderOperation,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> RenderedImage:
        del prepared, options, operation, materialization_policy
        async with self._lock:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        if self.failure is not None:
            raise self.failure
        await anyio.sleep(0.01)
        async with self._lock:
            self.active -= 1
        return self.result


def _executor(
    budget: HtmlRenderBudget,
    *,
    result: RenderedImage | None = None,
) -> tuple[BudgetedPreparedHtmlExecutor, _Executor]:
    inner = _Executor(result or rendered_image("png", width=2, height=2))
    return (
        BudgetedPreparedHtmlExecutor(
            inner,
            budget,
            provider_id="test-provider",
        ),
        inner,
    )


@pytest.mark.parametrize(
    ("operation", "field"),
    [
        (RenderOperation.HTML_TO_IMAGE, "html"),
        (RenderOperation.TEXT_TO_IMAGE, "text"),
        (RenderOperation.MARKDOWN_TO_IMAGE, "source"),
        (RenderOperation.TEMPLATE_TO_IMAGE, "template"),
        (RenderOperation.PREPARED_HTML_TO_IMAGE, "prepared"),
    ],
)
@pytest.mark.anyio
async def test_html_budget_attributes_oversized_source_to_outer_caller(
    operation: RenderOperation,
    field: str,
) -> None:
    executor, inner = _executor(HtmlRenderBudget(max_source_bytes=3))

    with pytest.raises(InvalidRenderInputError, match="source bytes") as raised:
        await executor.execute(
            parse_html("<p>large</p>"),
            RasterOptions(width=1, height=1, device_pixel_ratio=1),
            operation=operation,
        )

    assert raised.value.operation == operation.value
    assert raised.value.field == field
    assert inner.calls == 0


@pytest.mark.parametrize(
    "prepared",
    [
        parse_html("", stylesheets=["four"]),
        parse_html("", assets=[PreparedAsset("memory:asset", b"four")]),
    ],
)
@pytest.mark.anyio
async def test_html_budget_counts_every_prepared_payload(
    prepared: PreparedHtml,
) -> None:
    executor, inner = _executor(HtmlRenderBudget(max_source_bytes=3))

    with pytest.raises(InvalidRenderInputError, match="4 source bytes"):
        await executor.execute(
            prepared,
            RasterOptions(width=1, height=1),
            operation=RenderOperation.PREPARED_HTML_TO_IMAGE,
        )

    assert inner.calls == 0


def test_html_budget_rejects_non_html_operation_identity() -> None:
    budget = HtmlRenderBudget()

    with pytest.raises(ValueError, match="does not execute prepared HTML"):
        budget.validate_request(
            parse_html(""),
            RasterOptions(),
            operation=RenderOperation.TEMPLATE_TO_HTML,
        )


@pytest.mark.anyio
async def test_html_budget_rejects_explicit_physical_pixels_before_provider() -> None:
    executor, inner = _executor(HtmlRenderBudget(max_pixels=15))

    with pytest.raises(InvalidRenderInputError, match="16 physical pixels") as raised:
        await executor.execute(
            parse_html(""),
            RasterOptions(width=2, height=2, device_pixel_ratio=2),
            operation=RenderOperation.HTML_TO_IMAGE,
        )

    assert raised.value.field == "raster.dimensions"
    assert inner.calls == 0


@pytest.mark.anyio
async def test_html_budget_rejects_device_pixel_ratio_before_provider() -> None:
    executor, inner = _executor(HtmlRenderBudget(max_device_pixel_ratio=2))

    with pytest.raises(InvalidRenderInputError, match="device_pixel_ratio") as raised:
        await executor.execute(
            parse_html(""),
            RasterOptions(width=1, height=None, device_pixel_ratio=3),
            operation=RenderOperation.HTML_TO_IMAGE,
        )

    assert raised.value.field == "raster.device_pixel_ratio"
    assert inner.calls == 0


@pytest.mark.anyio
async def test_html_budget_validates_content_driven_output() -> None:
    oversized = rendered_image("png", width=4, height=5)
    executor, inner = _executor(
        HtmlRenderBudget(max_pixels=19, max_auto_height=4),
        result=oversized,
    )

    with pytest.raises(RenderOutputLimitError) as raised:
        await executor.execute(
            parse_html(""),
            RasterOptions(width=4, height=None, device_pixel_ratio=1),
            operation=RenderOperation.HTML_TO_IMAGE,
        )

    assert raised.value.operation == RenderOperation.HTML_TO_IMAGE.value
    assert raised.value.limit == "pixels"
    assert (raised.value.actual, raised.value.maximum) == (20, 19)
    assert inner.calls == 1


@pytest.mark.anyio
async def test_html_budget_validates_content_driven_height() -> None:
    tall = rendered_image("png", width=2, height=5)
    executor, _ = _executor(
        HtmlRenderBudget(max_pixels=100, max_auto_height=4),
        result=tall,
    )

    with pytest.raises(RenderOutputLimitError) as raised:
        await executor.execute(
            parse_html(""),
            RasterOptions(width=2, height=None, device_pixel_ratio=1),
            operation=RenderOperation.HTML_TO_IMAGE,
        )

    assert raised.value.limit == "auto_height"
    assert (raised.value.actual, raised.value.maximum) == (5, 4)


@pytest.mark.anyio
async def test_html_budget_validates_encoded_output_size() -> None:
    result = rendered_image("png", width=1, height=1)
    executor, _ = _executor(
        HtmlRenderBudget(max_output_bytes=len(result.data) - 1),
        result=result,
    )

    with pytest.raises(RenderOutputLimitError) as raised:
        await executor.execute(
            parse_html(""),
            RasterOptions(width=1, height=1, device_pixel_ratio=1),
            operation=RenderOperation.HTML_TO_IMAGE,
        )

    assert raised.value.limit == "bytes"
    assert raised.value.actual == len(result.data)
    assert raised.value.maximum == len(result.data) - 1


@pytest.mark.anyio
async def test_html_budget_concurrency_is_shared_across_callers() -> None:
    executor, inner = _executor(HtmlRenderBudget(max_concurrency=2))

    async def render() -> None:
        await executor.execute(
            parse_html(""),
            RasterOptions(width=1, height=1, device_pixel_ratio=1),
            operation=RenderOperation.HTML_TO_IMAGE,
        )

    async with anyio.create_task_group() as group:
        for _ in range(8):
            group.start_soon(render)

    assert inner.calls == 8
    assert inner.max_active == 2


@pytest.mark.anyio
async def test_html_budget_translates_raw_provider_failure_with_caller_identity() -> (
    None
):
    executor, inner = _executor(HtmlRenderBudget())
    inner.failure = RuntimeError("third-party failure")

    with pytest.raises(ProviderExecutionError, match="third-party failure") as raised:
        await executor.execute(
            parse_html("<p>failure</p>"),
            RasterOptions(),
            operation=RenderOperation.MARKDOWN_TO_IMAGE,
        )

    assert raised.value.provider_id == "test-provider"
    assert raised.value.operation == RenderOperation.MARKDOWN_TO_IMAGE.value


@pytest.mark.anyio
async def test_html_budget_preserves_stable_provider_failure() -> None:
    executor, inner = _executor(HtmlRenderBudget())
    expected = InvalidRenderInputError(
        "provider-specific validation",
        operation=RenderOperation.TEXT_TO_IMAGE.value,
        field="text",
    )
    inner.failure = expected

    with pytest.raises(InvalidRenderInputError) as raised:
        await executor.execute(
            parse_html("<p>failure</p>"),
            RasterOptions(),
            operation=RenderOperation.TEXT_TO_IMAGE,
        )

    assert raised.value is expected


@pytest.mark.anyio
async def test_html_budget_recontexts_misattributed_provider_execution() -> None:
    executor, inner = _executor(HtmlRenderBudget())
    inner.failure = ProviderExecutionError(
        "backend-internal operation failed",
        provider_id="wrong-provider",
        operation="native.render",
        retryable=True,
    )

    with pytest.raises(ProviderExecutionError) as raised:
        await executor.execute(
            parse_html("<p>failure</p>"),
            RasterOptions(),
            operation=RenderOperation.TEMPLATE_TO_IMAGE,
        )

    assert raised.value.provider_id == "test-provider"
    assert raised.value.operation == RenderOperation.TEMPLATE_TO_IMAGE.value
    assert raised.value.retryable is True
    assert raised.value.__cause__ is inner.failure


@pytest.mark.anyio
async def test_html_budget_preserves_correctly_attributed_provider_execution() -> None:
    executor, inner = _executor(HtmlRenderBudget())
    expected = ProviderExecutionError(
        "provider failed",
        provider_id="test-provider",
        operation=RenderOperation.HTML_TO_IMAGE.value,
    )
    inner.failure = expected

    with pytest.raises(ProviderExecutionError) as raised:
        await executor.execute(
            parse_html(""),
            RasterOptions(),
            operation=RenderOperation.HTML_TO_IMAGE,
        )

    assert raised.value is expected


def test_html_budget_exposes_configured_limits() -> None:
    budget = HtmlRenderBudget(
        max_source_bytes=1,
        max_pixels=2,
        max_output_bytes=3,
        max_device_pixel_ratio=4,
        max_auto_height=5,
        max_concurrency=6,
    )

    assert budget.max_source_bytes == 1
    assert budget.max_pixels == 2
    assert budget.max_output_bytes == 3
    assert budget.max_device_pixel_ratio == 4
    assert budget.max_auto_height == 5
    assert budget.max_concurrency == 6


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_source_bytes", 0),
        ("max_pixels", 0),
        ("max_output_bytes", 0),
        ("max_device_pixel_ratio", 0),
        ("max_auto_height", 0),
        ("max_concurrency", 0),
    ],
)
def test_html_budget_rejects_invalid_limits(field: str, value: int) -> None:
    with pytest.raises(ValueError, match=field):
        if field == "max_source_bytes":
            HtmlRenderBudget(max_source_bytes=value)
        elif field == "max_pixels":
            HtmlRenderBudget(max_pixels=value)
        elif field == "max_output_bytes":
            HtmlRenderBudget(max_output_bytes=value)
        elif field == "max_device_pixel_ratio":
            HtmlRenderBudget(max_device_pixel_ratio=value)
        elif field == "max_auto_height":
            HtmlRenderBudget(max_auto_height=value)
        else:
            HtmlRenderBudget(max_concurrency=value)
