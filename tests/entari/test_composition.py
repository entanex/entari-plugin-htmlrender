from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import anyio
import anyio.lowlevel
import pytest

from entari_plugin_htmlrender.composition import (
    _select_observers,
    build_runtime_plan,
)
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    ProviderConfigurationError,
    ProviderUnavailableError,
    ResourceAccessDeniedError,
    RuntimeUnavailableError,
)
from entari_plugin_htmlrender.providers.sdk import (
    ProviderAvailable,
    ProviderBinding,
    ProviderDependencies,
    ProviderId,
    ProviderUnavailable,
)
from entari_plugin_htmlrender.rendering import NoopOperationObserver
from entari_plugin_htmlrender.resources import FileResourceRef
from entari_plugin_htmlrender.resources.config import (
    LocalResourceStrategy,
    RemoteLocalResourcePolicy,
    RemoteResourceStrategy,
    ResourceStrategy,
)
from entari_plugin_htmlrender.resources.observation import NoopCacheObserver
from tests.image_fixtures import rendered_image

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from entari_plugin_htmlrender.preparation.models import (
        PreparedHtml,
        RasterOptions,
    )
    from entari_plugin_htmlrender.rendering import RenderOperation
    from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
    from entari_plugin_htmlrender.resources.config import (
        ResourceMaterializationPolicy,
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
    calls: list[tuple[PreparedHtml, RasterOptions, RenderOperation]] = field(
        default_factory=list
    )

    async def execute(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        operation: RenderOperation,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> RenderedImage:
        del materialization_policy
        self.calls.append((prepared, options, operation))
        return rendered_image("png", width=1600, height=733)


class _FakeProvider:
    id = ProviderId("fake-provider")

    def __init__(
        self,
        *,
        available: bool = True,
        strategy: ResourceStrategy | None = None,
    ) -> None:
        self.available = available
        self.strategy = strategy or LocalResourceStrategy()
        self.parsed: list[Mapping[str, object]] = []
        self.composed_config: list[object] = []
        self.dependencies: list[ProviderDependencies] = []
        self.lifecycle = _FakeLifecycle()
        self.executor = _FakeExecutor()

    def parse_config(self, raw: Mapping[str, object]) -> object:
        self.parsed.append(dict(raw))
        return {"parsed": dict(raw)}

    def check_availability(
        self,
        config: object,
    ) -> ProviderAvailable | ProviderUnavailable:
        del config
        if self.available:
            return ProviderAvailable()
        return ProviderUnavailable("provider missing", retryable=False)

    def resource_strategy(self, config: object) -> ResourceStrategy:
        del config
        return self.strategy

    def compose(
        self,
        config: object,
        dependencies: ProviderDependencies,
    ) -> ProviderBinding:
        self.composed_config.append(config)
        self.dependencies.append(dependencies)
        return ProviderBinding(
            lifecycle=self.lifecycle,
            prepared_html_executor=self.executor,
        )


def test_observer_selection_follows_configuration_flags() -> None:
    off = HtmlRenderConfig()
    on = HtmlRenderConfig.model_validate({"observability": {"prometheus": True}})

    operation_off, cache_off = _select_observers(off)
    operation_on, cache_on = _select_observers(on)

    assert isinstance(operation_off, NoopOperationObserver)
    assert isinstance(cache_off, NoopCacheObserver)
    assert type(operation_on).__name__ == "TelemetryOperationObserver"
    assert type(cache_on).__name__ == "TelemetryCacheObserver"


async def test_composition_owns_local_access_security(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed.txt"
    outside = tmp_path.parent / "outside.txt"
    allowed.write_text("allowed", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")
    config = HtmlRenderConfig.model_validate(
        {
            "resources": {
                "local_access": {
                    "allowed_paths": [tmp_path],
                }
            }
        }
    )
    runtime = build_runtime_plan(config).build_runtime()

    assert await runtime.resources.fetch_text(FileResourceRef(allowed)) == "allowed"
    with pytest.raises(ResourceAccessDeniedError, match="outside allowed roots"):
        await runtime.resources.fetch(FileResourceRef(outside))

    await runtime.aclose()


def test_runtime_plan_is_consumed_by_exactly_one_runtime() -> None:
    plan = build_runtime_plan(HtmlRenderConfig())

    runtime = plan.build_runtime()

    assert plan.provider is None
    assert runtime.renderer.supported_operations == frozenset()
    with pytest.raises(InvalidRenderInputError) as captured:
        plan.build_runtime()
    assert captured.value.operation == "runtime.build"
    assert captured.value.field == "plan"


def test_runtime_plan_configuration_is_detached(tmp_path: Path) -> None:
    config = HtmlRenderConfig.model_validate(
        {
            "resources": {
                "local_access": {
                    "allowed_paths": [tmp_path],
                }
            }
        }
    )
    plan = build_runtime_plan(config)

    config.resources.local_access.allowed_paths.append(tmp_path.parent)
    exposed = plan.config
    exposed.resources.local_access.allowed_paths.append(tmp_path.parent)

    assert plan.config.resources.local_access.allowed_paths == [tmp_path]


def test_runtime_plan_preserves_opaque_provider_config_identity() -> None:
    class OpaqueConfig:
        def __deepcopy__(self, memo: object) -> object:
            del memo
            raise AssertionError("provider-owned config must not be copied")

    opaque = OpaqueConfig()

    class OpaqueProvider(_FakeProvider):
        def parse_config(self, raw: Mapping[str, object]) -> object:
            del raw
            return opaque

    provider = OpaqueProvider()
    plan = build_runtime_plan(
        HtmlRenderConfig.model_validate(
            {"provider": "fake-provider", "provider_config": {"answer": 42}}
        ),
        provider_override=provider,
    )

    plan.build_runtime()

    assert provider.composed_config == [opaque]


async def test_available_provider_receives_narrow_dependencies_and_renders() -> None:
    strategy = RemoteResourceStrategy()
    provider = _FakeProvider(strategy=strategy)
    plan = build_runtime_plan(
        HtmlRenderConfig.model_validate(
            {"provider": "fake-provider", "provider_config": {"answer": 42}}
        ),
        provider_override=provider,
    )
    runtime = plan.build_runtime()

    assert provider.parsed == [{"answer": 42}]
    dependencies = provider.dependencies[0]
    assert dependencies.resources.strategy is strategy
    assert not hasattr(dependencies.resources, "materialize_template_variables")
    assert dependencies.asset_publisher is None

    artifact = await runtime.renderer.rasterize_html("<p>hi</p>")
    assert (artifact.format, artifact.width, artifact.height) == ("png", 1600, 733)
    await runtime.aclose()


async def test_provider_capability_admission_drains_with_runtime_shutdown() -> None:
    provider = _FakeProvider()
    runtime = build_runtime_plan(
        HtmlRenderConfig.model_validate({"provider": "fake-provider"}),
        provider_override=provider,
    ).build_runtime()
    admission = provider.dependencies[0].operation_admission
    entered = anyio.Event()
    release = anyio.Event()
    closed = anyio.Event()

    async def provider_operation() -> None:
        async with admission.operation("provider.custom"):
            entered.set()
            await release.wait()

    async def close_runtime() -> None:
        await runtime.aclose()
        closed.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(provider_operation)
        await entered.wait()
        task_group.start_soon(close_runtime)
        await anyio.lowlevel.checkpoint()
        assert not closed.is_set()
        release.set()

    assert closed.is_set()
    with pytest.raises(RuntimeUnavailableError):
        async with admission.operation("provider.custom"):
            pass


_FILEHOST_CONFIG = {
    "provider": "fake-provider",
    "resources": {
        "filehost": {"public_base_url": "http://assets.example/htmlrender"},
    },
}


async def test_filehost_strategy_composes_one_publisher_and_server() -> None:
    provider = _FakeProvider(
        strategy=RemoteResourceStrategy(
            local_resource_policy=RemoteLocalResourcePolicy.FILEHOST,
        )
    )
    plan = build_runtime_plan(
        HtmlRenderConfig.model_validate(_FILEHOST_CONFIG),
        provider_override=provider,
    )
    runtime = plan.build_runtime()

    assert plan.hosted_asset_server is not None
    assert plan.asset_publisher_settings is not None
    assert provider.dependencies[0].asset_publisher is not None

    await runtime.aclose()
    await plan.hosted_asset_server.aclose()


def test_filehost_strategy_requires_public_base_url() -> None:
    provider = _FakeProvider(
        strategy=RemoteResourceStrategy(
            local_resource_policy=RemoteLocalResourcePolicy.FILEHOST,
        )
    )

    with pytest.raises(ProviderConfigurationError, match="public_base_url"):
        build_runtime_plan(
            HtmlRenderConfig.model_validate({"provider": "fake-provider"}),
            provider_override=provider,
        )


async def test_unavailable_provider_preserves_reason_and_identity() -> None:
    provider = _FakeProvider(available=False)
    runtime = build_runtime_plan(
        HtmlRenderConfig.model_validate({"provider": "fake-provider"}),
        provider_override=provider,
    ).build_runtime()

    assert provider.dependencies == []
    with pytest.raises(ProviderUnavailableError) as render_error:
        await runtime.renderer.rasterize_html("<p>hi</p>")
    assert render_error.value.provider_id == "fake-provider"
    assert render_error.value.reason == "provider missing"

    with pytest.raises(ProviderUnavailableError) as startup_error:
        await runtime.startup()
    assert startup_error.value.operation == "startup"
    await runtime.aclose()
