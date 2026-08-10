"""Playwright engine provider: settings, availability, and composition.

Browser modules are imported lazily so that loading the plugin with
``startup: off`` never pulls the Playwright package until the first render.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol, final

from entari_plugin_htmlrender.adapters._lease import (
    ExecutionLeaseProvider,
    PreparedHtmlLeaseExecutor,
)
from entari_plugin_htmlrender.adapters.playwright.config import PlaywrightConfig
from entari_plugin_htmlrender.errors import (
    HtmlRenderError,
    ProviderConfigurationError,
    ProviderError,
)
from entari_plugin_htmlrender.providers.sdk import (
    PLAYWRIGHT_PROVIDER_ID,
    ProviderAvailability,
    ProviderBinding,
    ProviderDependencies,
    ProviderId,
)
from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog
from entari_plugin_htmlrender.resources.config import (
    LocalResourceStrategy,
    RemoteResourceStrategy,
    ResourceMaterializationPolicy,
    ResourceStrategy,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from entari_plugin_htmlrender.adapters.playwright.render import PlaywrightLease
    from entari_plugin_htmlrender.preparation.models import (
        PreparedHtml,
        RasterOptions,
    )
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.ports import (
        AssetPublisher,
        ProviderResourceAccess,
    )


class _PlaywrightEngine(Protocol):
    """Lease operations supplied by the native Playwright engine."""

    async def create_lease(self) -> PlaywrightLease: ...

    def is_alive(self, lease: PlaywrightLease) -> bool: ...

    async def close_lease(self, lease: PlaywrightLease) -> None: ...


@final
class _LazyPlaywrightEngine:
    """Resolve the optional native engine at the first lifecycle operation."""

    def __init__(
        self,
        config: PlaywrightConfig,
        *,
        operation_observer: OperationObserver,
    ) -> None:
        self._config = config.model_copy(deep=True)
        self._operation_observer = operation_observer
        self._engine: _PlaywrightEngine | None = None

    def _resolve(self) -> _PlaywrightEngine:
        engine = self._engine
        if engine is not None:
            return engine
        from entari_plugin_htmlrender.adapters.playwright.render import (  # noqa: PLC0415
            PlaywrightEngine,
        )

        engine = PlaywrightEngine(
            self._config,
            operation_observer=self._operation_observer,
        )
        self._engine = engine
        return engine

    async def create_lease(self) -> PlaywrightLease:
        return await self._resolve().create_lease()

    def is_alive(self, lease: PlaywrightLease) -> bool:
        return self._resolve().is_alive(lease)

    async def close_lease(self, lease: PlaywrightLease) -> None:
        await self._resolve().close_lease(lease)


_OBSERVATION_ATTRIBUTES: dict[str, str] = {"render.backend": PLAYWRIGHT_PROVIDER_ID}


@contextmanager
def _translate(
    operation: str,
    runtime_error: type[ProviderError],
) -> Iterator[None]:
    """Translate native Playwright failures into the stable error model."""
    try:
        yield
    except HtmlRenderError:
        raise
    except Exception as error:
        raise runtime_error(
            f"Playwright {operation} failed.",
            provider_id=str(PLAYWRIGHT_PROVIDER_ID),
            operation=operation,
            source=error,
        ) from error


async def _rasterize(
    lease: PlaywrightLease,
    prepared: PreparedHtml,
    options: RasterOptions,
    materialization_policy: ResourceMaterializationPolicy | None,
    *,
    resources: ProviderResourceAccess,
    asset_publisher: AssetPublisher | None,
) -> RenderedImage:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        PageConfig,
        RenderConfig,
        ViewportConfig,
        _build_screenshot_config,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )

    viewport_height = options.height if options.height is not None else 10
    render = RenderConfig(
        page=PageConfig(
            viewport=ViewportConfig(
                width=options.width,
                height=viewport_height,
            ),
        ),
        screenshot=_build_screenshot_config(
            options.format,
            quality=options.quality,
            device_scale_factor=options.device_pixel_ratio,
            screenshot_timeout=30_000,
            full_page=options.height is None,
            wait_before_screenshot=0,
        ),
    )
    data = await render_prepared_html(
        prepared,
        content=ContentConfig(html=prepared.html),
        render=render,
        lease=lease,
        resources=resources,
        asset_publisher=asset_publisher,
        resolve_mode=(
            materialization_policy or resources.strategy.materialization_policy
        ),
        telemetry_op="playwright.html_render.rasterize_html",
    )
    return RenderedImage.from_bytes(data, expected_format=options.format)


async def _probe(lease: PlaywrightLease) -> None:
    from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
        PageContext,
    )

    async with PageContext(lease).open():
        return


@final
class PlaywrightProvider:
    """First-party render provider backed by Playwright."""

    id: ProviderId = PLAYWRIGHT_PROVIDER_ID

    def parse_config(self, raw: Mapping[str, object]) -> PlaywrightConfig:
        return PlaywrightConfig.model_validate(dict(raw))

    def check_availability(self, config: PlaywrightConfig) -> ProviderAvailability:
        config = self._narrow(config)
        from entari_plugin_htmlrender.adapters.playwright.availability import (  # noqa: PLC0415
            playwright_availability,
        )

        return playwright_availability(config)

    def resource_strategy(self, config: PlaywrightConfig) -> ResourceStrategy:
        config = self._narrow(config)
        if config.connect_ws.endpoint or config.connect_cdp.endpoint:
            return RemoteResourceStrategy(
                materialization_policy=config.materialization_policy,
                local_resource_policy=config.remote_local_resource_policy,
            )
        return LocalResourceStrategy(
            materialization_policy=config.materialization_policy,
            local_resource_policy=config.local_local_resource_policy,
        )

    def compose(
        self,
        config: PlaywrightConfig,
        dependencies: ProviderDependencies,
    ) -> ProviderBinding:
        config = self._narrow(config)

        from entari_plugin_htmlrender.adapters.playwright.capabilities import (  # noqa: PLC0415
            PlaywrightCapabilityAdapter,
        )
        from entari_plugin_htmlrender.capabilities import (  # noqa: PLC0415
            PLAYWRIGHT,
        )

        engine = _LazyPlaywrightEngine(
            config,
            operation_observer=dependencies.operation_observer,
        )
        leases = ExecutionLeaseProvider(
            create=engine.create_lease,
            is_alive=engine.is_alive,
            close=engine.close_lease,
            provider_id=str(PLAYWRIGHT_PROVIDER_ID),
            observer=dependencies.operation_observer,
            translate=_translate,
            observation_attributes=_OBSERVATION_ATTRIBUTES,
            probe=_probe,
        )

        async def rasterize(
            lease: PlaywrightLease,
            prepared: PreparedHtml,
            options: RasterOptions,
            materialization_policy: ResourceMaterializationPolicy | None,
        ) -> RenderedImage:
            return await _rasterize(
                lease,
                prepared,
                options,
                materialization_policy,
                resources=dependencies.resources,
                asset_publisher=dependencies.asset_publisher,
            )

        executor = PreparedHtmlLeaseExecutor(
            leases=leases,
            rasterize=rasterize,
            translate=_translate,
            observer=dependencies.operation_observer,
            telemetry_operation="playwright.html_render.rasterize_html",
            observation_attributes=_OBSERVATION_ATTRIBUTES,
        )
        adapter = PlaywrightCapabilityAdapter(
            leases,
            dependencies.operation_observer,
            operation_admission=dependencies.operation_admission,
        )
        capabilities = CapabilityCatalog().with_capability(PLAYWRIGHT, adapter)
        return ProviderBinding(
            lifecycle=leases,
            prepared_html_executor=executor,
            provider_capabilities=capabilities,
        )

    @staticmethod
    def _narrow(settings: object) -> PlaywrightConfig:
        if not isinstance(settings, PlaywrightConfig):
            raise ProviderConfigurationError(
                "Playwright provider received settings that were not produced "
                "by parse_config().",
                provider_id=str(PLAYWRIGHT_PROVIDER_ID),
                operation="compose",
            )
        return settings


PROVIDER = PlaywrightProvider()

__all__ = ["PROVIDER", "PlaywrightProvider"]
