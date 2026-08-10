from __future__ import annotations

import sys
import types
from typing import TYPE_CHECKING, final, get_type_hints

import pytest

from entari_plugin_htmlrender.adapters.resources import (
    AnyioWorkerExecutor,
    CompositeResourceFetcher,
    ConfiguredLocalAccessPolicy,
    RemoteTransportExecutor,
)
from entari_plugin_htmlrender.errors import (
    ProviderConfigurationError,
    ProviderConflictError,
    ProviderNotFoundError,
    ProviderSelectionError,
)
from entari_plugin_htmlrender.providers import discovery
from entari_plugin_htmlrender.providers.sdk import (
    RESERVED_PROVIDER_IDS,
    LocalResourceStrategy,
    ProviderAvailability,
    ProviderAvailable,
    ProviderBinding,
    ProviderDependencies,
    ProviderId,
    RenderProvider,
)
from entari_plugin_htmlrender.rendering import (
    NoopOperationObserver,
    OperationAdmissionGate,
)
from entari_plugin_htmlrender.rendering.observers import NoopCacheObserver
from entari_plugin_htmlrender.resources.service import ResourceService

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from pytest_mock import MockerFixture

    from entari_plugin_htmlrender.resources.config import ResourceStrategy


class FakeProvider:
    def __init__(self, provider_id: str) -> None:
        self.id = ProviderId(provider_id)

    def parse_config(self, raw: Mapping[str, object]) -> object:
        return dict(raw)

    def check_availability(self, config: object) -> ProviderAvailability:
        del config
        return ProviderAvailable()

    def resource_strategy(self, config: object) -> ResourceStrategy:
        del config
        return LocalResourceStrategy()

    def compose(
        self,
        config: object,
        dependencies: ProviderDependencies,
    ) -> ProviderBinding:
        del config, dependencies
        raise NotImplementedError


def _entry_point(name: str, target: object) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        name=name,
        dist=f"dist-{name} 1.0",
        load=lambda: target,
    )


def _raise(message: str) -> None:
    raise RuntimeError(message)


def test_explicit_override_wins_even_for_reserved_ids() -> None:
    override = FakeProvider("takumi")

    resolved = discovery.resolve_provider(
        ProviderId("takumi"),
        provider_override=override,
    )

    assert resolved is override


def test_only_first_party_provider_ids_are_reserved() -> None:
    assert {"playwright", "takumi"} == RESERVED_PROVIDER_IDS


@pytest.mark.parametrize("provider_id", ["", " ", "Upper", "bad/id", "-bad"])
def test_invalid_configured_provider_ids_rejected(provider_id: str) -> None:
    with pytest.raises(ProviderConfigurationError, match="is invalid"):
        discovery.resolve_provider(
            ProviderId(provider_id),
        )


def test_explicit_override_must_match_selected_provider() -> None:
    with pytest.raises(ProviderConfigurationError, match="mismatched id"):
        discovery.resolve_provider(
            ProviderId("selected"),
            provider_override=FakeProvider("different"),
        )


def test_unknown_provider_raises_not_found(mocker: MockerFixture) -> None:
    mocker.patch.object(discovery, "entry_points", return_value=[])

    with pytest.raises(ProviderNotFoundError, match="'missing'"):
        discovery.resolve_provider(ProviderId("missing"))


def test_entry_point_provider_resolves(mocker: MockerFixture) -> None:
    provider = FakeProvider("thirdparty")
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("thirdparty", provider)],
    )

    assert discovery.resolve_provider(ProviderId("thirdparty")) is provider


def test_entry_point_class_is_instantiated(mocker: MockerFixture) -> None:
    @final
    class ClassProvider(FakeProvider):
        def __init__(self) -> None:
            super().__init__("classy")

    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("classy", ClassProvider)],
    )

    resolved = discovery.resolve_provider(ProviderId("classy"))

    assert isinstance(resolved, ClassProvider)


def test_entry_point_load_failure_is_structured(mocker: MockerFixture) -> None:
    entry_point = types.SimpleNamespace(
        name="broken",
        dist="dist-broken 1.0",
        load=lambda: _raise("load failed"),
    )
    mocker.patch.object(discovery, "entry_points", return_value=[entry_point])

    with pytest.raises(ProviderSelectionError) as raised:
        discovery.resolve_provider(ProviderId("broken"))

    assert raised.value.provider_id == "broken"
    assert raised.value.operation == "load_provider_entry_point"
    assert raised.value.causes[0].message == "load failed"


def test_entry_point_constructor_failure_is_structured(
    mocker: MockerFixture,
) -> None:
    @final
    class BrokenProvider(FakeProvider):
        def __init__(self) -> None:
            raise RuntimeError("constructor failed")

    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("broken", BrokenProvider)],
    )

    with pytest.raises(ProviderSelectionError) as raised:
        discovery.resolve_provider(ProviderId("broken"))

    assert raised.value.provider_id == "broken"
    assert raised.value.operation == "construct_provider"
    assert raised.value.causes[0].message == "constructor failed"


def test_entry_point_id_property_failure_is_structured(
    mocker: MockerFixture,
) -> None:
    class BrokenIdProvider(FakeProvider):
        def __init__(self) -> None:
            pass

        @property
        def id(self) -> ProviderId:
            raise RuntimeError("id failed")

    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("broken", BrokenIdProvider())],
    )

    with pytest.raises(ProviderSelectionError) as raised:
        discovery.resolve_provider(ProviderId("broken"))

    assert raised.value.provider_id == "broken"
    assert raised.value.operation == "inspect_provider_id"
    assert raised.value.causes[0].message == "id failed"


def test_entry_point_id_mismatch_rejected(mocker: MockerFixture) -> None:
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("alias", FakeProvider("real-id"))],
    )

    with pytest.raises(ProviderConfigurationError, match="mismatched id"):
        discovery.resolve_provider(ProviderId("alias"))


def test_duplicate_entry_points_rejected(mocker: MockerFixture) -> None:
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[
            _entry_point("dup", FakeProvider("dup")),
            _entry_point("dup", FakeProvider("dup")),
        ],
    )

    with pytest.raises(ProviderConflictError, match="Multiple entry points"):
        discovery.resolve_provider(ProviderId("dup"))


def test_invalid_entry_point_object_rejected(mocker: MockerFixture) -> None:
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("bogus", object())],
    )

    with pytest.raises(ProviderSelectionError, match="RenderProvider"):
        discovery.resolve_provider(ProviderId("bogus"))


def test_reserved_id_cannot_be_hijacked_by_entry_points(
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("takumi", FakeProvider("takumi"))],
    )

    with pytest.raises(ProviderConflictError, match="reserved"):
        discovery.resolve_provider(ProviderId("takumi"))


@pytest.fixture
def fake_first_party(mocker: MockerFixture) -> Iterator[FakeProvider]:
    provider = FakeProvider("takumi")
    module = types.ModuleType("tests_fake_takumi_provider")
    setattr(module, "PROVIDER", provider)  # noqa: B010 -- dynamic module attribute
    sys.modules["tests_fake_takumi_provider"] = module
    mocker.patch.dict(
        discovery._FIRST_PARTY_MODULES,
        {"takumi": "tests_fake_takumi_provider"},
    )
    yield provider
    sys.modules.pop("tests_fake_takumi_provider", None)


def test_reserved_id_loads_first_party_module(
    mocker: MockerFixture,
    fake_first_party: FakeProvider,
) -> None:
    mocker.patch.object(discovery, "entry_points", return_value=[])

    assert discovery.resolve_provider(ProviderId("takumi")) is fake_first_party


def test_first_party_import_failure_is_structured(mocker: MockerFixture) -> None:
    mocker.patch.object(discovery, "entry_points", return_value=[])
    mocker.patch.object(
        discovery,
        "import_module",
        side_effect=RuntimeError("import failed"),
    )

    with pytest.raises(ProviderSelectionError) as raised:
        discovery.resolve_provider(ProviderId("takumi"))

    assert raised.value.provider_id == "takumi"
    assert raised.value.operation == "import_first_party_provider"
    assert raised.value.causes[0].message == "import failed"


def test_resolve_provider_revalidates_public_id() -> None:
    with pytest.raises(ProviderConfigurationError) as raised:
        discovery.resolve_provider(ProviderId("Bad/Id"))

    assert raised.value.provider_id == "Bad/Id"
    assert raised.value.operation == "validate_provider_id"


def test_provider_dependencies_shape() -> None:
    worker = AnyioWorkerExecutor()
    local_access = ConfiguredLocalAccessPolicy(allowed_roots=(), allow_any=False)
    fetcher = CompositeResourceFetcher(
        worker,
        local_access=local_access,
        remote_transport=RemoteTransportExecutor(max_concurrent_fetches=2),
    )
    resources = ResourceService(
        fetcher=fetcher,
        local_access=local_access,
        strategy=LocalResourceStrategy(),
    )
    dependencies = ProviderDependencies(
        operation_observer=NoopOperationObserver(),
        operation_admission=OperationAdmissionGate(),
        cache_observer=NoopCacheObserver(),
        resources=resources,
        asset_publisher=None,
    )

    assert dependencies.operation_observer is not None
    assert dependencies.operation_admission is not None
    assert dependencies.cache_observer is not None
    assert dependencies.resources is resources
    assert dependencies.asset_publisher is None


def test_provider_sdk_annotations_are_runtime_resolvable() -> None:
    assert set(get_type_hints(ProviderDependencies)) == {
        "asset_publisher",
        "cache_observer",
        "operation_admission",
        "operation_observer",
        "resources",
    }
    assert set(get_type_hints(ProviderBinding)) == {
        "lifecycle",
        "prepared_html_executor",
        "provider_capabilities",
    }
    assert set(get_type_hints(RenderProvider.parse_config)) == {"raw", "return"}
    assert set(get_type_hints(RenderProvider.check_availability)) == {
        "config",
        "return",
    }
    assert set(get_type_hints(RenderProvider.compose)) == {
        "config",
        "dependencies",
        "return",
    }
