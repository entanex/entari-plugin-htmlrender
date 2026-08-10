from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import anyio
import anyio.lowlevel

from entari_plugin_htmlrender import (
    RasterOptions,
    RenderOperation,
    TemplateRef,
    parse_html,
)
from entari_plugin_htmlrender.graphics import RasterEncodeOptions
from entari_plugin_htmlrender.providers.sdk import ProviderBinding
from entari_plugin_htmlrender.rendering import (
    CapabilityCatalog,
    CapabilityKey,
)
from entari_plugin_htmlrender.resources import ResourceContent
from entari_plugin_htmlrender.runtime import RuntimeState
from entari_plugin_htmlrender.runtime.composition import build_runtime
from tests.image_fixtures import rendered_image

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from entari_plugin_htmlrender.graphics import RasterScene
    from entari_plugin_htmlrender.preparation.models import PreparedHtml
    from entari_plugin_htmlrender.rendering.artifacts import (
        RenderedImage,
    )
    from entari_plugin_htmlrender.resources import (
        InlineResource,
        PublishedResource,
        ResourceMaterializationPolicy,
        ResourceRef,
    )


@dataclass
class _FakeLifecycle:
    startup_calls: int = 0
    close_calls: int = 0

    async def startup(self) -> None:
        self.startup_calls += 1

    async def probe(self) -> None:
        return None

    async def aclose(self) -> None:
        self.close_calls += 1


@dataclass
class _FakeExecutor:
    calls: list[
        tuple[
            PreparedHtml,
            RasterOptions,
            RenderOperation,
            ResourceMaterializationPolicy | None,
        ]
    ] = field(default_factory=list)
    entered: anyio.Event | None = None
    release: anyio.Event | None = None
    result: RenderedImage = field(
        default_factory=lambda: rendered_image("png", width=1600, height=731)
    )

    async def execute(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        operation: RenderOperation,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> RenderedImage:
        self.calls.append((prepared, options, operation, materialization_policy))
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            await self.release.wait()
        return self.result


@dataclass
class _FakePreparer:
    template_html: str = "<p>rendered template</p>"

    async def prepare_html(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> PreparedHtml:
        return parse_html(html, base_url=base_url)

    async def prepare_text(
        self,
        text: str,
        *,
        stylesheet: ResourceRef | None = None,
    ) -> PreparedHtml:
        del stylesheet
        return parse_html(f"<p>{text}</p>")

    async def prepare_markdown(
        self,
        source: str | ResourceRef,
        *,
        stylesheet: ResourceRef | None = None,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml:
        del stylesheet, materialization_policy
        return parse_html(f"<p>{source}</p>")

    async def prepare_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
        *,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml:
        del template, variables, materialization_policy
        return parse_html(self.template_html)

    async def render_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
    ) -> str:
        del template, variables
        return self.template_html


class _FakeResources:
    async def fetch(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> ResourceContent:
        del resource, refresh
        return ResourceContent(b"content")

    async def fetch_bytes(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> bytes:
        return (await self.fetch(resource, refresh=refresh)).data

    async def fetch_text(
        self,
        resource: ResourceRef,
        *,
        encoding: str = "utf-8",
        errors: str = "strict",
        refresh: bool = False,
    ) -> str:
        return (await self.fetch_bytes(resource, refresh=refresh)).decode(
            encoding,
            errors,
        )

    @asynccontextmanager
    async def publish(
        self,
        content: ResourceContent | InlineResource,
        *,
        suffix: str | None = None,
    ) -> AsyncIterator[PublishedResource]:
        del content, suffix
        raise AssertionError("publish is not exercised by this test double")
        yield


_DEFAULT_GRAPHICS_OUTPUT = RasterEncodeOptions()


class _FakeGraphics:
    async def rasterize(
        self,
        scene: RasterScene,
        *,
        output: RasterEncodeOptions = _DEFAULT_GRAPHICS_OUTPUT,
    ) -> RenderedImage:
        del scene, output
        return rendered_image()


class _Marker:
    pass


def _build(
    *,
    lifecycle: _FakeLifecycle | None = None,
    executor: _FakeExecutor | None = None,
    capabilities: CapabilityCatalog | None = None,
):
    return build_runtime(
        binding=ProviderBinding(
            lifecycle=lifecycle or _FakeLifecycle(),
            prepared_html_executor=executor,
            provider_capabilities=capabilities,
        ),
        provider_id="fake",
        preparer=_FakePreparer(),
        resources=_FakeResources(),
        graphics=_FakeGraphics(),
    )


async def _wait_for_state(runtime, state: RuntimeState) -> None:
    while runtime.state is not state:
        await anyio.lowlevel.checkpoint()


def test_build_runtime_binds_five_raster_operations_and_capabilities() -> None:
    marker = _Marker()
    key = CapabilityKey("test.marker", _Marker)
    runtime = _build(
        executor=_FakeExecutor(),
        capabilities=CapabilityCatalog().with_capability(key, marker),
    )

    assert runtime.renderer.supported_operations == frozenset(
        {
            RenderOperation.HTML_TO_IMAGE,
            RenderOperation.TEXT_TO_IMAGE,
            RenderOperation.MARKDOWN_TO_IMAGE,
            RenderOperation.TEMPLATE_TO_IMAGE,
            RenderOperation.PREPARED_HTML_TO_IMAGE,
        }
    )
    assert runtime.capabilities.require(key) is marker


async def test_provider_without_executor_still_renders_template_to_html(
    tmp_path,
) -> None:
    runtime = _build()

    assert runtime.renderer.supported_operations == frozenset()
    artifact = await runtime.templates.render(
        TemplateRef(tmp_path, "page.html"),
        {"title": "hello"},
    )

    assert str(artifact) == "<p>rendered template</p>"


async def test_built_runtime_rasterizes_html_through_preparer_and_provider() -> None:
    executor = _FakeExecutor()
    runtime = _build(executor=executor)

    artifact = await runtime.renderer.rasterize_html(
        "<p>hello</p>",
        raster=RasterOptions(width=800, device_pixel_ratio=2),
    )

    assert artifact is executor.result
    prepared, options, operation, policy = executor.calls[0]
    assert "<p>hello</p>" in prepared.html
    assert options.width == 800
    assert operation is RenderOperation.HTML_TO_IMAGE
    assert policy is None


async def test_renderer_operation_is_admitted_for_full_execution_span() -> None:
    lifecycle = _FakeLifecycle()
    executor = _FakeExecutor(entered=anyio.Event(), release=anyio.Event())
    runtime = _build(lifecycle=lifecycle, executor=executor)
    close_finished = anyio.Event()

    async def render() -> None:
        await runtime.renderer.rasterize_html("<p>in flight</p>")

    async def close() -> None:
        await runtime.aclose()
        close_finished.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(render)
        assert executor.entered is not None
        await executor.entered.wait()
        task_group.start_soon(close)
        await _wait_for_state(runtime, RuntimeState.CLOSING)

        assert runtime.state is RuntimeState.CLOSING
        assert lifecycle.close_calls == 0
        assert executor.release is not None
        executor.release.set()
        await close_finished.wait()

    assert lifecycle.close_calls == 1
    assert runtime.state is RuntimeState.CLOSED
