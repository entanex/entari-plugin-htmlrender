from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pytest

from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    ProviderConfigurationError,
    ProviderSelectionError,
)
from entari_plugin_htmlrender.providers.sdk import (
    LocalResourceStrategy,
    ProviderAvailability,
    ProviderAvailable,
    ProviderBinding,
    ProviderDependencies,
    ProviderId,
    ProviderUnavailable,
)
from entari_plugin_htmlrender.resources.config import (
    LocalLocalResourcePolicy,
    RemoteLocalResourcePolicy,
    RemoteResourceStrategy,
    ResourceMaterializationPolicy,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from entari_plugin_htmlrender.providers.sdk import ResourceStrategy
    from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog


@dataclass
class _Lifecycle:
    async def startup(self) -> None:
        return None

    async def probe(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


class _Provider:
    id = ProviderId("boundary")

    def __init__(self) -> None:
        self.parse_failure: BaseException | None = None
        self.strategy_failure: BaseException | None = None
        self.availability_failure: BaseException | None = None
        self.compose_failure: BaseException | None = None
        self.parsed_config: object = {}
        self.strategy: object = LocalResourceStrategy()
        self.availability: object = ProviderAvailable()
        self.binding: object = ProviderBinding(lifecycle=_Lifecycle())

    def parse_config(self, raw: Mapping[str, object]) -> object:
        if self.parse_failure is not None:
            raise self.parse_failure
        del raw
        return self.parsed_config

    def resource_strategy(self, config: object) -> ResourceStrategy:
        del config
        if self.strategy_failure is not None:
            raise self.strategy_failure
        return cast("ResourceStrategy", self.strategy)

    def check_availability(self, config: object) -> ProviderAvailability:
        del config
        if self.availability_failure is not None:
            raise self.availability_failure
        return cast("ProviderAvailability", self.availability)

    def compose(
        self,
        config: object,
        dependencies: ProviderDependencies,
    ) -> ProviderBinding:
        del config, dependencies
        if self.compose_failure is not None:
            raise self.compose_failure
        return cast("ProviderBinding", self.binding)


def _config() -> HtmlRenderConfig:
    return HtmlRenderConfig(provider=ProviderId("boundary"))


def test_plan_rejects_wrong_config_type_with_stable_input_error() -> None:
    with pytest.raises(InvalidRenderInputError) as raised:
        build_runtime_plan(cast("HtmlRenderConfig", object()))

    assert raised.value.operation == "runtime.plan.build"
    assert raised.value.field == "config"


@pytest.mark.parametrize("phase", ["parse", "strategy"])
def test_configuration_boundary_translates_provider_failures(phase: str) -> None:
    provider = _Provider()
    failure = ValueError(f"{phase} failed")
    if phase == "parse":
        provider.parse_failure = failure
        operation = "parse_config"
    else:
        provider.strategy_failure = failure
        operation = "select_resource_strategy"

    with pytest.raises(ProviderConfigurationError) as raised:
        build_runtime_plan(_config(), provider_override=provider)

    assert raised.value.provider_id == "boundary"
    assert raised.value.operation == operation
    assert raised.value.causes[0].message == f"{phase} failed"


def test_plan_rejects_invalid_resource_strategy_shape() -> None:
    provider = _Provider()
    provider.strategy = object()

    with pytest.raises(ProviderConfigurationError) as raised:
        build_runtime_plan(_config(), provider_override=provider)

    assert raised.value.operation == "select_resource_strategy"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: LocalResourceStrategy(
            materialization_policy=cast(
                "ResourceMaterializationPolicy",
                "invalid",
            )
        ),
        lambda: LocalResourceStrategy(
            local_resource_policy=cast("LocalLocalResourcePolicy", "invalid")
        ),
        lambda: RemoteResourceStrategy(
            materialization_policy=cast(
                "ResourceMaterializationPolicy",
                "invalid",
            )
        ),
        lambda: RemoteResourceStrategy(
            local_resource_policy=cast("RemoteLocalResourcePolicy", "invalid")
        ),
    ],
)
def test_resource_strategy_values_reject_invalid_discriminants(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize(
    "availability",
    [
        lambda: ProviderUnavailable(cast("str", object())),
        lambda: ProviderUnavailable("missing", retryable=cast("bool", 1)),
    ],
)
def test_provider_unavailability_requires_stable_fields(
    availability: Callable[[], object],
) -> None:
    with pytest.raises(ValueError):
        availability()


def test_none_is_a_valid_provider_owned_parsed_config() -> None:
    provider = _Provider()
    provider.parsed_config = None

    plan = build_runtime_plan(_config(), provider_override=provider)
    runtime = plan.build_runtime()

    assert runtime.state.value == "open"


@pytest.mark.parametrize("phase", ["availability", "compose"])
def test_build_translates_provider_boundary_failures(phase: str) -> None:
    provider = _Provider()
    failure = RuntimeError(f"{phase} failed")
    if phase == "availability":
        provider.availability_failure = failure
        operation = "check_availability"
    else:
        provider.compose_failure = failure
        operation = "compose_provider"

    plan = build_runtime_plan(_config(), provider_override=provider)
    with pytest.raises(ProviderSelectionError) as raised:
        plan.build_runtime()

    assert raised.value.provider_id == "boundary"
    assert raised.value.operation == operation
    assert raised.value.causes[0].message == f"{phase} failed"


def test_build_rejects_invalid_availability_shape() -> None:
    provider = _Provider()
    provider.availability = None
    plan = build_runtime_plan(_config(), provider_override=provider)

    with pytest.raises(ProviderSelectionError) as raised:
        plan.build_runtime()

    assert raised.value.operation == "check_availability"


@pytest.mark.parametrize(
    "binding",
    [
        object(),
        ProviderBinding(lifecycle=cast("_Lifecycle", object())),
        ProviderBinding(
            lifecycle=_Lifecycle(),
            provider_capabilities=cast("CapabilityCatalog", object()),
        ),
    ],
)
def test_build_rejects_invalid_binding_shape(binding: object) -> None:
    provider = _Provider()
    provider.binding = binding
    plan = build_runtime_plan(_config(), provider_override=provider)

    with pytest.raises(ProviderSelectionError) as raised:
        plan.build_runtime()

    assert raised.value.operation in {"compose_provider", "validate_provider_binding"}
