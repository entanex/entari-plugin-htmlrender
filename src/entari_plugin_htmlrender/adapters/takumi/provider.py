"""Takumi engine provider: settings, availability, and composition."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, final

from entari_plugin_htmlrender.adapters._lease import (
    ExecutionLeaseProvider,
    PreparedHtmlLeaseExecutor,
)
from entari_plugin_htmlrender.adapters.takumi.capabilities import (
    TakumiCapabilityAdapter,
)
from entari_plugin_htmlrender.adapters.takumi.config import TakumiConfig
from entari_plugin_htmlrender.adapters.takumi.errors import (
    TakumiBackendError,
    TakumiInputError,
    TakumiResourceError,
    TakumiUnsupportedError,
)
from entari_plugin_htmlrender.adapters.takumi.operations import (
    rasterize_html as takumi_rasterize_html,
)
from entari_plugin_htmlrender.adapters.takumi.render import (
    OBSERVATION_ATTRIBUTES as _OBSERVATION_ATTRIBUTES,
)
from entari_plugin_htmlrender.adapters.takumi.render import TakumiEngine
from entari_plugin_htmlrender.adapters.takumi.runtime import require_runtime_state
from entari_plugin_htmlrender.capabilities import TAKUMI
from entari_plugin_htmlrender.errors import (
    HtmlRenderError,
    InvalidRenderInputError,
    ProviderConfigurationError,
    ProviderError,
    ResourceFetchError,
    UnsupportedDocumentFeatureError,
)
from entari_plugin_htmlrender.preparation import RasterOptions, parse_html
from entari_plugin_htmlrender.providers.sdk import (
    TAKUMI_PROVIDER_ID,
    ProviderAvailability,
    ProviderBinding,
    ProviderDependencies,
    ProviderId,
)
from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog
from entari_plugin_htmlrender.resources.config import (
    LocalResourceStrategy,
    ResourceMaterializationPolicy,
    ResourceStrategy,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from entari_plugin_htmlrender.preparation.models import PreparedHtml

    from .runtime import TakumiRuntimeState

_PROBE_HTML = '<div style="width:1px;height:1px"></div>'


@contextmanager
def _translate(
    operation: str,
    runtime_error: type[ProviderError],
) -> Iterator[None]:
    """Translate native Takumi failures into the stable error model."""
    try:
        yield
    except TakumiUnsupportedError as error:
        raise UnsupportedDocumentFeatureError(
            operation,
            error.feature,
            provider_id=str(TAKUMI_PROVIDER_ID),
        ) from error
    except TakumiInputError as error:
        raise InvalidRenderInputError(
            "Takumi rejected the prepared render input.",
            operation=operation,
            field=error.field,
            source=error,
        ) from error
    except TakumiResourceError as error:
        raise ResourceFetchError(
            "Takumi could not resolve a prepared resource.",
            reference=error.reference,
            operation=operation,
            source=error,
        ) from error
    except TakumiBackendError as error:
        raise runtime_error(
            f"Takumi {operation} failed.",
            provider_id=str(TAKUMI_PROVIDER_ID),
            operation=operation,
            source=error,
        ) from error
    except HtmlRenderError:
        raise
    except Exception as error:
        raise runtime_error(
            f"Takumi {operation} failed.",
            provider_id=str(TAKUMI_PROVIDER_ID),
            operation=operation,
            source=error,
        ) from error


async def _rasterize(
    state: TakumiRuntimeState,
    prepared: PreparedHtml,
    options: RasterOptions,
    materialization_policy: ResourceMaterializationPolicy | None,
    *,
    default_materialization_policy: ResourceMaterializationPolicy,
) -> RenderedImage:
    data = await takumi_rasterize_html(
        require_runtime_state(state),
        prepared,
        options,
        resolve_mode=materialization_policy or default_materialization_policy,
    )
    return RenderedImage.from_bytes(data, expected_format=options.format)


async def _probe(state: TakumiRuntimeState) -> None:
    state = require_runtime_state(state)
    await takumi_rasterize_html(
        state,
        parse_html(_PROBE_HTML),
        RasterOptions(width=8, height=8, device_pixel_ratio=1.0),
    )


@final
class TakumiProvider:
    """First-party render provider backed by Takumi."""

    id: ProviderId = TAKUMI_PROVIDER_ID

    def parse_config(self, raw: Mapping[str, object]) -> TakumiConfig:
        return TakumiConfig.model_validate(dict(raw))

    def check_availability(self, config: TakumiConfig) -> ProviderAvailability:
        self._narrow(config)
        from entari_plugin_htmlrender.adapters.takumi.render import (  # noqa: PLC0415
            takumi_availability,
        )

        return takumi_availability()

    def resource_strategy(self, config: TakumiConfig) -> ResourceStrategy:
        self._narrow(config)
        return LocalResourceStrategy()

    def compose(
        self,
        config: TakumiConfig,
        dependencies: ProviderDependencies,
    ) -> ProviderBinding:
        config = self._narrow(config)
        engine = TakumiEngine(
            config=config,
            operation_observer=dependencies.operation_observer,
            cache_observer=dependencies.cache_observer,
            resources=dependencies.resources,
        )
        leases = ExecutionLeaseProvider(
            create=engine.create_lease,
            is_alive=engine.is_alive,
            close=engine.close_lease,
            provider_id=str(TAKUMI_PROVIDER_ID),
            observer=dependencies.operation_observer,
            translate=_translate,
            observation_attributes=_OBSERVATION_ATTRIBUTES,
            probe=_probe,
        )

        async def rasterize(
            state: TakumiRuntimeState,
            prepared: PreparedHtml,
            options: RasterOptions,
            materialization_policy: ResourceMaterializationPolicy | None,
        ) -> RenderedImage:
            return await _rasterize(
                state,
                prepared,
                options,
                materialization_policy,
                default_materialization_policy=(
                    dependencies.resources.strategy.materialization_policy
                ),
            )

        executor = PreparedHtmlLeaseExecutor(
            leases=leases,
            rasterize=rasterize,
            translate=_translate,
            observer=dependencies.operation_observer,
            telemetry_operation="takumi.rasterize_html",
            observation_attributes=_OBSERVATION_ATTRIBUTES,
        )
        adapter = TakumiCapabilityAdapter(
            leases,
            dependencies.operation_observer,
            operation_admission=dependencies.operation_admission,
        )
        capabilities = CapabilityCatalog().with_capability(TAKUMI, adapter)
        return ProviderBinding(
            lifecycle=leases,
            prepared_html_executor=executor,
            provider_capabilities=capabilities,
        )

    @staticmethod
    def _narrow(settings: object) -> TakumiConfig:
        if not isinstance(settings, TakumiConfig):
            raise ProviderConfigurationError(
                "Takumi provider received settings that were not produced by "
                "parse_config().",
                provider_id=str(TAKUMI_PROVIDER_ID),
                operation="compose",
            )
        return settings


PROVIDER = TakumiProvider()

__all__ = ["PROVIDER", "TakumiProvider"]
