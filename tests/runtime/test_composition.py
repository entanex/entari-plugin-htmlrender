from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from entari_plugin_htmlrender.adapters.resources import (
    AnyioWorkerExecutor,
    ConfiguredLocalAccessPolicy,
    RemoteTransportExecutor,
    build_resource_reader,
)
from entari_plugin_htmlrender.preparation.service import DefaultHtmlPreparer
from entari_plugin_htmlrender.providers.sdk import EngineBindings
from entari_plugin_htmlrender.rendering import (
    CapabilityCatalog,
    CapabilityKey,
    RenderCommand,
    RenderedImage,
    RenderHtmlRequest,
    ResourcePolicy,
)
from entari_plugin_htmlrender.resources.config import (
    ResourceCacheSettings,
    ResourceStrategy,
)
from entari_plugin_htmlrender.resources.observation import NoopCacheObserver
from entari_plugin_htmlrender.resources.service import ResourceService
from entari_plugin_htmlrender.runtime import build_runtime
from tests.image_fixtures import rendered_image

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path
    from typing import Any

    from entari_plugin_htmlrender.preparation.models import (
        PreparedHtml,
        RasterOptions,
    )


@dataclass
class _FakeLifecycle:
    startup_calls: int = 0

    async def startup(self) -> None:
        self.startup_calls += 1

    async def probe(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


@dataclass
class _FakeExecutor:
    calls: list[tuple[PreparedHtml, RasterOptions]] = field(default_factory=list)
    result: RenderedImage = field(
        default_factory=lambda: rendered_image("png", width=1600, height=731)
    )

    async def execute(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        resource_policy: ResourcePolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage:
        del resource_policy, timeout_seconds
        self.calls.append((prepared, options))
        return self.result


class _FakeTemplateCompiler:
    async def render(
        self,
        template_path: object,
        template_name: str,
        variables: Mapping[str, Any],
        *,
        filters: Mapping[str, Callable[..., Any]] | None = None,
        immutable: bool = False,
        extensions: Sequence[object] = (),
    ) -> str:
        del template_path, template_name, variables, filters, immutable, extensions
        return ""

    async def clear(self) -> None:
        return None


class _Marker:
    pass


@pytest.fixture
def resources(tmp_path: Path) -> ResourceService:
    observer = NoopCacheObserver()
    worker = AnyioWorkerExecutor()
    return ResourceService(
        reader=build_resource_reader(
            ResourceCacheSettings(),
            observer,
            worker,
            remote_transport=RemoteTransportExecutor(max_concurrent_fetches=2),
        ),
        local_access=ConfiguredLocalAccessPolicy(
            allowed_roots=(tmp_path,),
            allow_any=False,
        ),
        strategy=ResourceStrategy(),
    )


@pytest.fixture
def preparer(resources: ResourceService) -> DefaultHtmlPreparer:
    worker = AnyioWorkerExecutor()
    return DefaultHtmlPreparer(
        resources=resources,
        templates=_FakeTemplateCompiler(),
        worker=worker,
    )


def test_build_runtime_with_executor_binds_all_use_cases(
    preparer: DefaultHtmlPreparer,
    resources: ResourceService,
) -> None:
    marker = _Marker()
    key = CapabilityKey("test.marker", _Marker)
    engine = EngineBindings(
        lifecycle=_FakeLifecycle(),
        prepared_html_executor=_FakeExecutor(),
        provider_capabilities=CapabilityCatalog().with_capability(key, marker),
    )

    runtime = build_runtime(
        engine=engine,
        preparer=preparer,
        resources=resources,
    )

    assert runtime.renderer.supported_commands == frozenset(
        {
            RenderCommand.HTML,
            RenderCommand.TEXT,
            RenderCommand.MARKDOWN,
            RenderCommand.TEMPLATE,
            RenderCommand.TEMPLATE_HTML,
            RenderCommand.RASTERIZE_HTML,
        }
    )
    assert runtime.extensions.require(key) is marker
    assert runtime.preparation is not preparer
    assert runtime.resources is not resources


def test_build_runtime_without_executor_only_renders_html(
    preparer: DefaultHtmlPreparer,
    resources: ResourceService,
) -> None:
    engine = EngineBindings(lifecycle=_FakeLifecycle())

    runtime = build_runtime(
        engine=engine,
        preparer=preparer,
        resources=resources,
    )

    assert runtime.renderer.supported_commands == frozenset(
        {RenderCommand.TEMPLATE_HTML}
    )


async def test_built_runtime_renders_through_real_preparer(
    preparer: DefaultHtmlPreparer,
    resources: ResourceService,
) -> None:
    executor = _FakeExecutor()
    engine = EngineBindings(
        lifecycle=_FakeLifecycle(),
        prepared_html_executor=executor,
    )
    runtime = build_runtime(
        engine=engine,
        preparer=preparer,
        resources=resources,
    )

    artifact = await runtime.renderer.render_html(
        RenderHtmlRequest(html="<p>hello</p>")
    )

    assert artifact is executor.result
    assert artifact.format == "png"
    assert (artifact.width, artifact.height) == (1600, 731)
    prepared, options = executor.calls[0]
    assert "<p>hello</p>" in prepared.html
    assert options.width == 800
