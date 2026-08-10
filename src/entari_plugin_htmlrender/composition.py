"""Framework-neutral composition root for one complete render runtime."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, final

import anyio
from exceptiongroup import BaseExceptionGroup

from entari_plugin_htmlrender.adapters.observability import (
    TelemetryCacheObserver,
    TelemetryOperationObserver,
)
from entari_plugin_htmlrender.adapters.resources import (
    AnyioWorkerExecutor,
    ConfiguredLocalAccessPolicy,
    ConfiguredRemoteAccessPolicy,
    FilehostAssetPublisher,
    HostedAssetHttpServer,
    HostedAssetStore,
    RemoteTransportExecutor,
    build_resource_fetcher,
)
from entari_plugin_htmlrender.adapters.templates import JinjaTemplateCompiler
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    ProviderConfigurationError,
    ProviderError,
    ProviderLifecycleError,
    ProviderSelectionError,
    ProviderUnavailableError,
    ResourcePublishError,
)
from entari_plugin_htmlrender.preparation.service import DefaultHtmlPreparer
from entari_plugin_htmlrender.providers.discovery import resolve_provider
from entari_plugin_htmlrender.providers.sdk import (
    ProviderAvailable,
    ProviderBinding,
    ProviderDependencies,
    ProviderUnavailable,
    RenderProvider,
)
from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
from entari_plugin_htmlrender.rendering.budget import HtmlRenderBudget
from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog
from entari_plugin_htmlrender.rendering.observers import (
    NoopCacheObserver,
    NoopOperationObserver,
)
from entari_plugin_htmlrender.resources._traversal import ResourceTraversalBudget
from entari_plugin_htmlrender.resources.config import (
    AssetPublisherSettings,
    LocalLocalResourcePolicy,
    LocalResourceStrategy,
    RemoteAccessSettings,
    RemoteLocalResourcePolicy,
    RemoteResourceStrategy,
    ResourceCacheSettings,
    ResourceMaterializationPolicy,
    ResourceStrategy,
)
from entari_plugin_htmlrender.resources.service import ResourceService
from entari_plugin_htmlrender.runtime.composition import build_runtime
from entari_plugin_htmlrender.runtime.runtime import RenderRuntime  # noqa: TC001

from ._graphics_composition import build_graphics_renderer
from .config import HtmlRenderConfig

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from entari_plugin_htmlrender.preparation.models import PreparedHtml, RasterOptions
    from entari_plugin_htmlrender.rendering.artifacts import RenderedImage
    from entari_plugin_htmlrender.rendering.models import RenderOperation
    from entari_plugin_htmlrender.rendering.ports import (
        OperationObserver,
        RuntimeLifecycle,
    )
    from entari_plugin_htmlrender.resources.models import ResourceRef
    from entari_plugin_htmlrender.resources.observation import CacheObserver
    from entari_plugin_htmlrender.resources.ports import AssetPublisher

_UNSET_PROVIDER_CONFIG = object()


@final
class _IdleLifecycle:
    async def startup(self) -> None:
        return None

    async def probe(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


@final
class _UnavailableProviderLifecycle:
    def __init__(
        self,
        provider_id: str,
        reason: str,
        *,
        retryable: bool,
    ) -> None:
        self._provider_id = provider_id
        self._reason = reason
        self._retryable = retryable

    def _error(self, operation: str) -> ProviderUnavailableError:
        return ProviderUnavailableError(
            self._provider_id,
            self._reason,
            operation=operation,
            retryable=self._retryable,
        )

    async def startup(self) -> None:
        raise self._error("startup")

    async def probe(self) -> None:
        raise self._error("probe")

    async def aclose(self) -> None:
        return None


@final
class _UnavailableProviderExecutor:
    def __init__(
        self,
        provider_id: str,
        reason: str,
        *,
        retryable: bool,
    ) -> None:
        self._provider_id = provider_id
        self._reason = reason
        self._retryable = retryable

    async def execute(
        self,
        prepared: PreparedHtml,
        options: RasterOptions,
        *,
        operation: RenderOperation,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> RenderedImage:
        del prepared, options, materialization_policy
        raise ProviderUnavailableError(
            self._provider_id,
            self._reason,
            operation=operation.value,
            retryable=self._retryable,
        )


@final
class _ProviderResourceView:
    """Expose exactly the policy-bound operations promised to Providers."""

    def __init__(self, delegate: ResourceService) -> None:
        self._delegate = delegate

    @property
    def strategy(self) -> ResourceStrategy:
        return self._delegate.strategy

    def authorize_local(self, path: Path) -> Path:
        return self._delegate.authorize_local(path)

    async def fetch_bytes(
        self,
        resource: ResourceRef,
        *,
        refresh: bool = False,
    ) -> bytes:
        return await self._delegate.fetch_bytes(resource, refresh=refresh)


@final
class _ComposedLifecycle:
    """Own startup rollback, poisoning, and best-effort reverse teardown."""

    def __init__(
        self,
        *,
        provider_id: str | None,
        provider: RuntimeLifecycle,
        resources: ResourceService,
        templates: JinjaTemplateCompiler,
        publisher: AssetPublisher | None,
        remote_transport: RemoteTransportExecutor,
    ) -> None:
        self._provider_id = provider_id
        self._provider = provider
        self._resources = resources
        self._templates = templates
        self._publisher = publisher
        self._remote_transport = remote_transport
        self._poisoned = False

    @staticmethod
    async def _cleanup(
        *operations: Callable[[], Awaitable[None]],
    ) -> list[BaseException]:
        errors: list[BaseException] = []
        with anyio.CancelScope(shield=True):
            for operation in operations:
                try:
                    await operation()
                except BaseException as error:  # noqa: PERF203
                    errors.append(error)
        return errors

    @staticmethod
    def _raise_errors(message: str, errors: list[BaseException]) -> None:
        if not errors:
            return
        if len(errors) == 1:
            raise errors[0]
        raise BaseExceptionGroup(message, errors)

    async def startup(self) -> None:
        if self._poisoned:
            raise ProviderLifecycleError(
                "The composition is poisoned by an incomplete startup rollback.",
                provider_id=self._provider_id,
                operation="startup",
                retryable=False,
            )

        steps: list[
            tuple[Callable[[], Awaitable[None]], Callable[[], Awaitable[None]]]
        ] = []
        if self._publisher is not None:
            steps.append((self._publisher.startup, self._publisher.clear))
        steps.append((self._provider.startup, self._provider.aclose))

        completed_undo: list[Callable[[], Awaitable[None]]] = []
        try:
            for start, undo in steps:
                await start()
                completed_undo.append(undo)
        except BaseException as error:
            rollback_errors = await self._cleanup(
                *reversed(completed_undo),
                self._templates.clear,
                self._resources.clear,
            )
            if rollback_errors:
                self._poisoned = True
                self._raise_errors(
                    "Render runtime startup and rollback both failed.",
                    [error, *rollback_errors],
                )
            raise

    async def probe(self) -> None:
        await self._provider.probe()

    async def aclose(self) -> None:
        operations: list[Callable[[], Awaitable[None]]] = [
            self._provider.aclose,
            self._templates.clear,
            self._resources.clear,
            self._remote_transport.aclose,
        ]
        if self._publisher is not None:
            operations.extend((self._publisher.clear, self._publisher.aclose))
        errors = await self._cleanup(*operations)
        self._raise_errors("Render runtime shutdown failed.", errors)


@final
class RuntimePlan:
    """Immutable inputs from which the host builds one isolated runtime graph."""

    __slots__ = (
        "_config",
        "_consumed",
        "_hosted_asset_server",
        "_hosted_asset_store",
        "_provider",
        "_provider_config",
        "_provider_id",
        "_resource_strategy",
    )

    def __init__(
        self,
        config: HtmlRenderConfig,
        provider: RenderProvider[Any] | None,
        provider_config: object | None,
        resource_strategy: ResourceStrategy,
        hosted_asset_store: HostedAssetStore | None = None,
        hosted_asset_server: HostedAssetHttpServer | None = None,
    ) -> None:
        self._config = config.model_copy(deep=True)
        self._consumed = False
        self._provider = provider
        self._provider_id = None if config.provider is None else str(config.provider)
        self._provider_config = provider_config
        self._resource_strategy = resource_strategy
        self._hosted_asset_store = hosted_asset_store
        self._hosted_asset_server = hosted_asset_server

    @property
    def config(self) -> HtmlRenderConfig:
        return self._config.model_copy(deep=True)

    @property
    def provider(self) -> RenderProvider[Any] | None:
        return self._provider

    @property
    def provider_id(self) -> str | None:
        return self._provider_id

    @property
    def resource_strategy(self) -> ResourceStrategy:
        return self._resource_strategy

    @property
    def hosted_asset_server(self) -> HostedAssetHttpServer | None:
        return self._hosted_asset_server

    def _inputs_for_build(self) -> tuple[HtmlRenderConfig, object]:
        return self._config.model_copy(deep=True), self._provider_config

    def build_runtime(self) -> RenderRuntime:
        """Consume this plan to build one graph without external I/O."""
        if self._consumed:
            raise InvalidRenderInputError(
                "RuntimePlan is one-shot; create a new plan for another runtime.",
                operation="runtime.build",
                field="plan",
            )
        self._consumed = True
        return _build_runtime_for(self)

    @property
    def asset_publisher_settings(self) -> AssetPublisherSettings | None:
        if not _uses_publisher(self.resource_strategy):
            return None
        return _publisher_settings(self.config)


def _select_observers(
    config: HtmlRenderConfig,
) -> tuple[OperationObserver, CacheObserver]:
    observability = config.observability
    if observability.sentry or observability.prometheus:
        return (
            TelemetryOperationObserver(
                sentry=observability.sentry,
                prometheus=observability.prometheus,
            ),
            TelemetryCacheObserver(
                sentry=observability.sentry,
                prometheus=observability.prometheus,
            ),
        )
    return NoopOperationObserver(), NoopCacheObserver()


def _cache_settings(config: HtmlRenderConfig) -> ResourceCacheSettings:
    cache = config.resources.cache
    return ResourceCacheSettings(
        max_entries=cache.max_entries,
        max_bytes=cache.max_bytes,
        max_resource_bytes=cache.max_resource_bytes,
        revalidate_seconds=cache.revalidate_seconds,
        template_environment_max_entries=(
            config.resources.templates.environment_cache_max_entries
        ),
        template_environment_cache_size=(
            config.resources.templates.environment_compiled_cache_size
        ),
    )


def _remote_access_settings(config: HtmlRenderConfig) -> RemoteAccessSettings:
    remote = config.resources.remote_access
    return RemoteAccessSettings(
        allow_private_networks=remote.allow_private_networks,
        allow_hosts=tuple(remote.allow_hosts),
        deny_hosts=tuple(remote.deny_hosts),
        max_redirects=remote.max_redirects,
        request_timeout_seconds=remote.request_timeout_seconds,
        max_concurrent_fetches=remote.max_concurrent_fetches,
    )


def _publisher_settings(config: HtmlRenderConfig) -> AssetPublisherSettings:
    filehost = config.resources.filehost
    return AssetPublisherSettings(
        cache_ttl_seconds=filehost.cache_ttl_seconds,
        request_header_name=filehost.request_header_name,
        request_header_value=filehost.request_header_value,
        request_header_salt=filehost.request_header_salt,
        prewarm_enabled=filehost.prewarm_enabled,
        prewarm_max_files=filehost.prewarm_max_files,
        prewarm_paths=tuple(filehost.prewarm_paths),
        prewarm_extensions=tuple(filehost.prewarm_extensions),
        max_resource_bytes=config.resources.cache.max_resource_bytes,
        public_base_url=filehost.public_base_url,
        max_entries=filehost.max_entries,
        max_bytes=filehost.max_bytes,
    )


def _uses_publisher(strategy: ResourceStrategy) -> bool:
    return strategy.local_resource_policy in {
        LocalLocalResourcePolicy.FILEHOST,
        RemoteLocalResourcePolicy.FILEHOST,
    }


def build_runtime_plan(
    config: HtmlRenderConfig,
    *,
    provider_override: RenderProvider[Any] | None = None,
) -> RuntimePlan:
    """Resolve and validate only the selected Provider; perform no runtime I/O."""
    if not isinstance(config, HtmlRenderConfig):
        raise InvalidRenderInputError(
            "config must be an HtmlRenderConfig value.",
            operation="runtime.plan.build",
            field="config",
        )
    if config.provider is None:
        return RuntimePlan(
            config,
            None,
            _UNSET_PROVIDER_CONFIG,
            LocalResourceStrategy(),
        )

    provider = resolve_provider(
        config.provider,
        provider_override=provider_override,
    )
    provider_id = str(config.provider)
    try:
        provider_config = provider.parse_config(config.provider_config)
    except ProviderError:
        raise
    except Exception as error:
        raise ProviderConfigurationError(
            f"Provider {provider_id!r} rejected its configuration.",
            provider_id=provider_id,
            operation="parse_config",
            source=error,
        ) from error
    try:
        strategy = provider.resource_strategy(provider_config)
    except ProviderError:
        raise
    except Exception as error:
        raise ProviderConfigurationError(
            f"Provider {provider_id!r} could not select a resource strategy.",
            provider_id=provider_id,
            operation="select_resource_strategy",
            source=error,
        ) from error
    if not isinstance(strategy, (LocalResourceStrategy, RemoteResourceStrategy)):
        raise ProviderConfigurationError(
            f"Provider {provider_id!r} returned an invalid resource strategy.",
            provider_id=provider_id,
            operation="select_resource_strategy",
        )
    if _uses_publisher(strategy) and config.resources.filehost.public_base_url is None:
        raise ProviderConfigurationError(
            "The selected resource strategy requires "
            "resources.filehost.public_base_url.",
            provider_id=str(provider.id),
            operation="build_runtime_plan",
        )

    store: HostedAssetStore | None = None
    server: HostedAssetHttpServer | None = None
    if _uses_publisher(strategy):
        publisher_settings = _publisher_settings(config)
        store = HostedAssetStore(
            max_entries=publisher_settings.max_entries,
            max_bytes=publisher_settings.max_bytes,
        )
        server = HostedAssetHttpServer(
            store,
            bind_host=config.resources.filehost.bind_host,
            bind_port=config.resources.filehost.bind_port,
        )
    return RuntimePlan(
        config,
        provider,
        provider_config,
        strategy,
        store,
        server,
    )


def _build_runtime_for(plan: RuntimePlan) -> RenderRuntime:
    config, parsed_provider_config = plan._inputs_for_build()
    operation_observer, cache_observer = _select_observers(config)
    cache_settings = _cache_settings(config)
    worker = AnyioWorkerExecutor()
    operation_admission = OperationAdmissionGate()
    graphics = build_graphics_renderer(
        config.graphics,
        worker=worker,
        observer=operation_observer,
        operation_admission=operation_admission,
    )

    local = config.resources.local_access
    local_access = ConfiguredLocalAccessPolicy(
        allowed_roots=local.allowed_paths,
        allow_any=local.allow_any_path,
    )
    remote_settings = _remote_access_settings(config)
    remote_access = ConfiguredRemoteAccessPolicy(remote_settings)
    remote_transport = RemoteTransportExecutor(
        max_concurrent_fetches=remote_settings.max_concurrent_fetches
    )
    fetcher = build_resource_fetcher(
        cache_settings,
        cache_observer,
        worker,
        local_access=local_access,
        remote_access=remote_access,
        remote_transport=remote_transport,
        remote_timeout_seconds=remote_settings.request_timeout_seconds,
    )

    strategy = plan.resource_strategy
    publisher: AssetPublisher | None = None
    if _uses_publisher(strategy):
        store = plan._hosted_asset_store
        if store is None:
            raise ResourcePublishError(
                "The filehost strategy has no hosted asset store.",
                reference=None,
                operation="build_runtime",
            )
        publisher = FilehostAssetPublisher(
            settings=_publisher_settings(config),
            observer=cache_observer,
            worker=worker,
            local_access=local_access,
            store=store,
        )

    resources = ResourceService(
        fetcher=fetcher,
        local_access=local_access,
        strategy=strategy,
        publisher=publisher,
        traversal_budget=ResourceTraversalBudget(
            max_nodes=config.resources.traversal.max_nodes,
            max_depth=config.resources.traversal.max_depth,
            max_concurrency=config.resources.traversal.max_concurrency,
        ),
    )
    templates = JinjaTemplateCompiler(
        max_entries=cache_settings.template_environment_max_entries,
        observer=cache_observer,
        worker=worker,
        local_access=local_access,
        cache_size=cache_settings.template_environment_cache_size,
    )
    preparer = DefaultHtmlPreparer(
        resources=resources,
        templates=templates,
        worker=worker,
    )

    provider = plan.provider
    provider_id = plan.provider_id
    if provider is None:
        binding = ProviderBinding(lifecycle=_IdleLifecycle())
    else:
        if provider_id is None:
            raise ProviderSelectionError(
                "The runtime plan lost its selected Provider identity.",
                provider_id=None,
                operation="build_runtime",
            )
        selected_provider_id = provider_id
        if parsed_provider_config is _UNSET_PROVIDER_CONFIG:
            raise ProviderConfigurationError(
                "The selected Provider has no parsed configuration.",
                provider_id=selected_provider_id,
                operation="build_runtime",
            )
        try:
            availability = provider.check_availability(parsed_provider_config)
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderSelectionError(
                f"Provider {selected_provider_id!r} availability check failed.",
                provider_id=selected_provider_id,
                operation="check_availability",
                source=error,
            ) from error
        if isinstance(availability, ProviderUnavailable):
            binding = ProviderBinding(
                lifecycle=_UnavailableProviderLifecycle(
                    selected_provider_id,
                    availability.reason,
                    retryable=availability.retryable,
                ),
                prepared_html_executor=_UnavailableProviderExecutor(
                    selected_provider_id,
                    availability.reason,
                    retryable=availability.retryable,
                ),
            )
        elif isinstance(availability, ProviderAvailable):
            try:
                binding = provider.compose(
                    parsed_provider_config,
                    ProviderDependencies(
                        operation_observer=operation_observer,
                        operation_admission=operation_admission,
                        cache_observer=cache_observer,
                        resources=_ProviderResourceView(resources),
                        asset_publisher=publisher,
                    ),
                )
            except ProviderError:
                raise
            except Exception as error:
                raise ProviderSelectionError(
                    f"Provider {selected_provider_id!r} composition failed.",
                    provider_id=selected_provider_id,
                    operation="compose_provider",
                    source=error,
                ) from error
            if not isinstance(binding, ProviderBinding):
                raise ProviderSelectionError(
                    f"Provider {selected_provider_id!r} returned an invalid binding.",
                    provider_id=selected_provider_id,
                    operation="compose_provider",
                )
            components = (
                (binding.lifecycle, ("startup", "probe", "aclose"), "lifecycle"),
                (
                    binding.prepared_html_executor,
                    ("execute",),
                    "prepared_html_executor",
                ),
            )
            for component, methods, field in components:
                if component is None and field == "prepared_html_executor":
                    continue
                try:
                    valid = component is not None and all(
                        callable(getattr(component, method)) for method in methods
                    )
                except Exception as error:
                    raise ProviderSelectionError(
                        f"Provider {selected_provider_id!r} binding field "
                        f"{field!r} could not be inspected.",
                        provider_id=selected_provider_id,
                        operation="validate_provider_binding",
                        source=error,
                    ) from error
                if not valid:
                    raise ProviderSelectionError(
                        f"Provider {selected_provider_id!r} binding field "
                        f"{field!r} is invalid.",
                        provider_id=selected_provider_id,
                        operation="validate_provider_binding",
                    )
            if binding.provider_capabilities is not None and not isinstance(
                binding.provider_capabilities,
                CapabilityCatalog,
            ):
                raise ProviderSelectionError(
                    f"Provider {selected_provider_id!r} binding field "
                    "'provider_capabilities' is invalid.",
                    provider_id=selected_provider_id,
                    operation="validate_provider_binding",
                )
        else:
            raise ProviderSelectionError(
                f"Provider {selected_provider_id!r} returned an invalid "
                "availability result.",
                provider_id=selected_provider_id,
                operation="check_availability",
            )

    lifecycle = _ComposedLifecycle(
        provider_id=provider_id,
        provider=binding.lifecycle,
        resources=resources,
        templates=templates,
        publisher=publisher,
        remote_transport=remote_transport,
    )
    return build_runtime(
        binding=replace(binding, lifecycle=lifecycle),
        provider_id=provider_id,
        preparer=preparer,
        resources=resources,
        graphics=graphics,
        operation_admission=operation_admission,
        html_render_budget=HtmlRenderBudget(
            max_source_bytes=config.html.max_source_bytes,
            max_pixels=config.html.max_pixels,
            max_output_bytes=config.html.max_output_bytes,
            max_device_pixel_ratio=config.html.max_device_pixel_ratio,
            max_auto_height=config.html.max_auto_height,
            max_concurrency=config.html.max_concurrency,
        ),
    )


__all__ = ["RuntimePlan", "build_runtime_plan"]
