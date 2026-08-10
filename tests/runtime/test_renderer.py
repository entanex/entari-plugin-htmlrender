from __future__ import annotations

from dataclasses import dataclass, field
from inspect import signature
from pathlib import Path
from typing import TYPE_CHECKING, cast, get_type_hints

import anyio
import pytest

from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    RenderTimeoutError,
    UnsupportedOperationError,
)
from entari_plugin_htmlrender.preparation import (
    PreparedHtml,
    RasterOptions,
    TemplateRef,
    parse_html,
)
from entari_plugin_htmlrender.rendering import OperationAdmissionGate, RenderedImage
from entari_plugin_htmlrender.rendering.contracts import HtmlRenderer, TemplateRenderer
from entari_plugin_htmlrender.rendering.models import RenderOperation
from entari_plugin_htmlrender.resources.config import (
    ResourceMaterializationPolicy,
)
from entari_plugin_htmlrender.resources.models import FileResourceRef, ResourceRef
from entari_plugin_htmlrender.runtime.bindings import _HtmlRendererBindings
from entari_plugin_htmlrender.runtime.renderer import (
    _DefaultHtmlRenderer,
    _DefaultTemplateRenderer,
)
from entari_plugin_htmlrender.runtime.use_cases import (
    _RasterizeHtml,
    _RasterizeMarkdown,
    _RasterizePrepared,
    _RasterizeTemplate,
    _RasterizeText,
    _RenderTemplate,
)
from tests.image_fixtures import rendered_image

if TYPE_CHECKING:
    from collections.abc import Mapping


PREPARED = parse_html("<p>prepared</p>")


@dataclass
class _ExecutorCall:
    prepared: PreparedHtml
    raster: RasterOptions
    operation: RenderOperation
    materialization_policy: ResourceMaterializationPolicy | None


@dataclass
class _FakeExecutor:
    result: RenderedImage = field(
        default_factory=lambda: rendered_image("png", width=1600, height=713)
    )
    calls: list[_ExecutorCall] = field(default_factory=list)
    delay: float = 0
    failure: BaseException | None = None

    async def execute(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        operation: RenderOperation,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> RenderedImage:
        if self.delay:
            await anyio.sleep(self.delay)
        if self.failure is not None:
            raise self.failure
        self.calls.append(
            _ExecutorCall(prepared, options, operation, materialization_policy)
        )
        return self.result


@dataclass
class _FakePreparer:
    prepared: PreparedHtml = PREPARED
    html_content: str = "<p>template html</p>"
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    delay: float = 0

    async def _wait(self) -> None:
        if self.delay:
            await anyio.sleep(self.delay)

    async def prepare_html(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> PreparedHtml:
        await self._wait()
        self.calls.append(("html", {"html": html, "base_url": base_url}))
        return self.prepared

    async def prepare_text(
        self,
        text: str,
        *,
        stylesheet: ResourceRef | None = None,
    ) -> PreparedHtml:
        await self._wait()
        self.calls.append(("text", {"text": text, "stylesheet": stylesheet}))
        return self.prepared

    async def prepare_markdown(
        self,
        source: str | ResourceRef,
        *,
        stylesheet: ResourceRef | None = None,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml:
        await self._wait()
        self.calls.append(
            (
                "markdown",
                {
                    "source": source,
                    "stylesheet": stylesheet,
                    "materialization_policy": materialization_policy,
                },
            )
        )
        return self.prepared

    async def prepare_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
        *,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml:
        await self._wait()
        self.calls.append(
            (
                "template",
                {
                    "template": template,
                    "variables": dict(variables),
                    "materialization_policy": materialization_policy,
                },
            )
        )
        return self.prepared

    async def render_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
    ) -> str:
        await self._wait()
        self.calls.append(
            (
                "template_html",
                {"template": template, "variables": dict(variables)},
            )
        )
        return self.html_content


def _full_renderers(
    result: RenderedImage | None = None,
    *,
    provider_id: str = "test-provider",
) -> tuple[
    _DefaultHtmlRenderer,
    _DefaultTemplateRenderer,
    _FakePreparer,
    _FakeExecutor,
]:
    preparer = _FakePreparer()
    executor = _FakeExecutor() if result is None else _FakeExecutor(result=result)
    gate = OperationAdmissionGate()
    renderer = _DefaultHtmlRenderer(
        _HtmlRendererBindings(
            rasterize_html=_RasterizeHtml(
                preparer=preparer,
                executor=executor,
            ),
            rasterize_text=_RasterizeText(
                preparer=preparer,
                executor=executor,
            ),
            rasterize_markdown=_RasterizeMarkdown(
                preparer=preparer,
                executor=executor,
            ),
            rasterize_template=_RasterizeTemplate(
                preparer=preparer,
                executor=executor,
            ),
            rasterize_prepared=_RasterizePrepared(executor=executor),
        ),
        operation_admission=gate,
        provider_id=provider_id,
    )
    templates = _DefaultTemplateRenderer(
        _RenderTemplate(preparer=preparer),
        operation_admission=gate,
        provider_id=provider_id,
    )
    return renderer, templates, preparer, executor


async def test_caller_first_raster_operations_return_typed_artifacts(
    tmp_path: Path,
) -> None:
    expected = rendered_image("jpeg", width=1280, height=960)
    renderer, _, preparer, executor = _full_renderers(expected)
    stylesheet = FileResourceRef(tmp_path / "theme.css")
    markdown = FileResourceRef(tmp_path / "readme.md")
    template = TemplateRef(tmp_path, "card.html")
    raster = RasterOptions(
        width=640,
        height=480,
        format="jpeg",
        quality=80,
    )

    artifacts = [
        await renderer.rasterize_html(
            "<p>hi</p>",
            raster=raster,
            base_url="https://example.invalid/",
            materialization_policy=ResourceMaterializationPolicy.STRICT,
        ),
        await renderer.rasterize_text(
            "hello",
            stylesheet=stylesheet,
            raster=raster,
        ),
        await renderer.rasterize_markdown(
            markdown,
            stylesheet=stylesheet,
            raster=raster,
        ),
        await renderer.rasterize_template(
            template,
            {"title": "hello"},
            raster=raster,
        ),
        await renderer.rasterize_prepared(PREPARED, raster=raster),
    ]

    assert artifacts == [expected] * 5
    assert [kind for kind, _ in preparer.calls] == [
        "html",
        "text",
        "markdown",
        "template",
    ]
    assert preparer.calls[2][1]["source"] is markdown
    assert preparer.calls[2][1]["stylesheet"] is stylesheet
    assert preparer.calls[3][1]["template"] == template
    assert executor.calls[0].materialization_policy is (
        ResourceMaterializationPolicy.STRICT
    )
    assert all(call.raster is raster for call in executor.calls)
    assert [call.operation for call in executor.calls] == [
        RenderOperation.HTML_TO_IMAGE,
        RenderOperation.TEXT_TO_IMAGE,
        RenderOperation.MARKDOWN_TO_IMAGE,
        RenderOperation.TEMPLATE_TO_IMAGE,
        RenderOperation.PREPARED_HTML_TO_IMAGE,
    ]


async def test_markdown_string_is_always_inline_even_when_empty() -> None:
    renderer, _, preparer, _ = _full_renderers()

    await renderer.rasterize_markdown("")
    await renderer.rasterize_markdown("notes/readme.md")

    assert [call[1]["source"] for call in preparer.calls] == [
        "",
        "notes/readme.md",
    ]


async def test_template_renderer_returns_rendered_html() -> None:
    _, templates, preparer, _ = _full_renderers()
    template = TemplateRef(Path("templates"), "card.html")

    artifact = await templates.render(template, {"name": "Akashina"})

    assert str(artifact) == "<p>template html</p>"
    assert preparer.calls == [
        (
            "template_html",
            {"template": template, "variables": {"name": "Akashina"}},
        )
    ]


@pytest.mark.parametrize("phase", ["preparation", "execution"])
async def test_total_deadline_has_one_public_error_taxonomy(phase: str) -> None:
    renderer, _, preparer, executor = _full_renderers()
    if phase == "preparation":
        preparer.delay = 0.1
    else:
        executor.delay = 0.1

    with pytest.raises(RenderTimeoutError) as exc_info:
        await renderer.rasterize_html(
            "<p>slow</p>",
            timeout_seconds=0.01,
        )

    assert exc_info.value.operation == RenderOperation.HTML_TO_IMAGE.value
    assert exc_info.value.timeout_seconds == 0.01


async def test_inner_timeout_is_not_misclassified_as_public_deadline() -> None:
    renderer, _, _, executor = _full_renderers()
    executor.failure = TimeoutError("provider timeout")

    with pytest.raises(TimeoutError, match="provider timeout"):
        await renderer.rasterize_html("<p>failure</p>", timeout_seconds=1)


async def test_missing_binding_preserves_provider_identity() -> None:
    renderer = _DefaultHtmlRenderer(
        _HtmlRendererBindings(),
        operation_admission=OperationAdmissionGate(),
        provider_id="minimal-provider",
    )

    with pytest.raises(UnsupportedOperationError) as exc_info:
        await renderer.rasterize_markdown("# unavailable")

    assert exc_info.value.operation == RenderOperation.MARKDOWN_TO_IMAGE.value
    assert exc_info.value.provider_id == "minimal-provider"


async def test_invalid_caller_values_use_structured_error() -> None:
    renderer, _, _, _ = _full_renderers()

    with pytest.raises(InvalidRenderInputError) as exc_info:
        await renderer.rasterize_html(
            "<p>bad raster</p>",
            raster=cast("RasterOptions", object()),
        )

    assert exc_info.value.operation == RenderOperation.HTML_TO_IMAGE.value
    assert exc_info.value.field == "raster"


@pytest.mark.parametrize("timeout_value", [True, "1", object()])
async def test_timeout_rejects_invalid_runtime_types(timeout_value: object) -> None:
    renderer, _, _, _ = _full_renderers()

    with pytest.raises(InvalidRenderInputError) as exc_info:
        await renderer.rasterize_html(
            "<p>bad timeout</p>",
            timeout_seconds=cast("float", timeout_value),
        )

    assert exc_info.value.operation == RenderOperation.HTML_TO_IMAGE.value
    assert exc_info.value.field == "timeout_seconds"


def test_default_implementations_satisfy_public_protocols() -> None:
    renderer, templates, _, _ = _full_renderers()

    assert isinstance(renderer, HtmlRenderer)
    assert isinstance(templates, TemplateRenderer)
    assert renderer.supported_operations == frozenset(
        {
            RenderOperation.HTML_TO_IMAGE,
            RenderOperation.TEXT_TO_IMAGE,
            RenderOperation.MARKDOWN_TO_IMAGE,
            RenderOperation.TEMPLATE_TO_IMAGE,
            RenderOperation.PREPARED_HTML_TO_IMAGE,
        }
    )
    assert renderer.supports(RenderOperation.MARKDOWN_TO_IMAGE)
    assert not renderer.supports(RenderOperation.TEMPLATE_TO_HTML)


def test_public_contract_annotations_are_runtime_resolvable() -> None:
    for method_name in (
        "rasterize_html",
        "rasterize_text",
        "rasterize_markdown",
        "rasterize_template",
        "rasterize_prepared",
    ):
        hints = get_type_hints(getattr(HtmlRenderer, method_name))
        assert hints["return"] is RenderedImage

    template_hints = get_type_hints(TemplateRenderer.render)
    assert template_hints["template"] is TemplateRef


def test_public_contract_has_no_request_or_jinja_extension_surface() -> None:
    for method_name in (
        "rasterize_html",
        "rasterize_text",
        "rasterize_markdown",
        "rasterize_template",
        "rasterize_prepared",
    ):
        parameters = signature(getattr(HtmlRenderer, method_name)).parameters
        assert "request" not in parameters
        assert "filters" not in parameters
        assert "extensions" not in parameters
        assert "width" not in parameters
        assert "height" not in parameters
        assert "raster" in parameters

    template_parameters = signature(TemplateRenderer.render).parameters
    assert "filters" not in template_parameters
    assert "extensions" not in template_parameters
