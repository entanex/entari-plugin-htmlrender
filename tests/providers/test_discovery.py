from __future__ import annotations

import sys
import types
from typing import TYPE_CHECKING, final, get_type_hints

import pytest

from entari_plugin_htmlrender.adapters.resources import (
    AnyioWorkerExecutor,
    CompositeResourceReader,
    ConfiguredLocalAccessPolicy,
    RemoteTransportExecutor,
)
from entari_plugin_htmlrender.providers import discovery
from entari_plugin_htmlrender.providers.sdk import (
    RESERVED_PROVIDER_IDS,
    EngineBindings,
    EngineId,
    EngineProvider,
    ProviderAvailability,
    ProviderDependencies,
)
from entari_plugin_htmlrender.rendering import (
    NoopOperationObserver,
    OperationAdmissionGate,
    ProviderNotFound,
    ProviderUnavailable,
)
from entari_plugin_htmlrender.rendering.observers import NoopCacheObserver
from entari_plugin_htmlrender.resources.config import ResourceStrategy
from entari_plugin_htmlrender.resources.service import ResourceService

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from pytest_mock import MockerFixture


class FakeProvider:
    def __init__(self, provider_id: EngineId) -> None:
        self.id = provider_id

    def parse_settings(self, raw: Mapping[str, object]) -> object:
        return dict(raw)

    def availability(self, settings: object) -> ProviderAvailability:
        del settings
        return ProviderAvailability(available=True)

    def resource_strategy(self, settings: object) -> ResourceStrategy:
        del settings
        return ResourceStrategy()

    def compose(
        self,
        settings: object,
        dependencies: ProviderDependencies,
    ) -> EngineBindings:
        del settings, dependencies
        raise NotImplementedError


def _entry_point(name: str, target: object) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        name=name,
        dist=f"dist-{name} 1.0",
        load=lambda: target,
    )


def test_explicit_override_wins_even_for_reserved_ids() -> None:
    override = FakeProvider("takumi")

    resolved = discovery.resolve_provider("takumi", explicit=[override])

    assert resolved is override


def test_only_first_party_provider_ids_are_reserved() -> None:
    assert {"playwright", "takumi"} == RESERVED_PROVIDER_IDS


def test_duplicate_explicit_ids_rejected() -> None:
    with pytest.raises(ProviderUnavailable, match="Duplicate explicit provider"):
        discovery.resolve_provider(
            "anything",
            explicit=[FakeProvider("dup"), FakeProvider("dup")],
        )


@pytest.mark.parametrize("provider_id", ["", " ", "Upper", "bad/id", "-bad"])
def test_invalid_explicit_provider_ids_rejected(provider_id: str) -> None:
    with pytest.raises(ProviderUnavailable, match="invalid provider id"):
        discovery.resolve_provider(
            "anything",
            explicit=[FakeProvider(provider_id)],
        )


def test_unknown_provider_raises_not_found(mocker: MockerFixture) -> None:
    mocker.patch.object(discovery, "entry_points", return_value=[])

    with pytest.raises(ProviderNotFound, match="`missing`"):
        discovery.resolve_provider("missing")


def test_entry_point_provider_resolves(mocker: MockerFixture) -> None:
    provider = FakeProvider("thirdparty")
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("thirdparty", provider)],
    )

    assert discovery.resolve_provider("thirdparty") is provider


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

    resolved = discovery.resolve_provider("classy")

    assert isinstance(resolved, ClassProvider)


def test_entry_point_id_mismatch_rejected(mocker: MockerFixture) -> None:
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("alias", FakeProvider("real-id"))],
    )

    with pytest.raises(ProviderUnavailable, match="mismatched id"):
        discovery.resolve_provider("alias")


def test_duplicate_entry_points_rejected(mocker: MockerFixture) -> None:
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[
            _entry_point("dup", FakeProvider("dup")),
            _entry_point("dup", FakeProvider("dup")),
        ],
    )

    with pytest.raises(ProviderUnavailable, match="Multiple entry points"):
        discovery.resolve_provider("dup")


def test_invalid_entry_point_object_rejected(mocker: MockerFixture) -> None:
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("bogus", object())],
    )

    with pytest.raises(ProviderUnavailable, match="EngineProvider"):
        discovery.resolve_provider("bogus")


def test_reserved_id_cannot_be_hijacked_by_entry_points(
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(
        discovery,
        "entry_points",
        return_value=[_entry_point("takumi", FakeProvider("takumi"))],
    )

    with pytest.raises(ProviderUnavailable, match="reserved"):
        discovery.resolve_provider("takumi")


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

    assert discovery.resolve_provider("takumi") is fake_first_party


def test_provider_dependencies_shape() -> None:
    worker = AnyioWorkerExecutor()
    reader = CompositeResourceReader(
        worker,
        remote_transport=RemoteTransportExecutor(max_concurrent_fetches=2),
    )
    local_access = ConfiguredLocalAccessPolicy(allowed_roots=(), allow_any=False)
    resources = ResourceService(
        reader=reader,
        local_access=local_access,
        strategy=ResourceStrategy(),
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
    assert set(get_type_hints(EngineBindings)) == {
        "lifecycle",
        "prepared_html_executor",
        "provider_capabilities",
    }
    assert set(get_type_hints(EngineProvider.parse_settings)) == {"raw", "return"}
    assert set(get_type_hints(EngineProvider.compose)) == {
        "settings",
        "dependencies",
        "return",
    }
