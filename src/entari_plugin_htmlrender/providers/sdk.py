"""Provider SDK: the formal contract between the plugin and render engines.

A provider is loaded either from an explicit composition-root override or
from the ``entari_plugin_htmlrender.providers`` entry-point group. Settings
flow through the provider opaquely: the composition root calls
``parse_settings`` and hands the result straight back to ``availability`` and
``compose``. Providers narrow the settings
object internally; this keeps entry-point loading fully typed without
generics over dynamically discovered classes.
"""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003 -- runtime annotation contract
from dataclasses import dataclass
import re
from typing import Final, Protocol, TypeAlias, TypeVar, runtime_checkable

from entari_plugin_htmlrender.rendering.capabilities import (  # noqa: TC001
    CapabilityCatalog,
)
from entari_plugin_htmlrender.rendering.ports import (  # noqa: TC001
    OperationAdmission,
    OperationObserver,
    PreparedHtmlExecutor,
    RuntimeLifecycle,
)
from entari_plugin_htmlrender.resources.config import ResourceStrategy
from entari_plugin_htmlrender.resources.observation import (  # noqa: TC001
    CacheObserver,
)
from entari_plugin_htmlrender.resources.ports import (  # noqa: TC001
    AssetPublisher,
    ProviderResources,
)

EngineId: TypeAlias = str
SettingsT = TypeVar("SettingsT")

ENTRY_POINT_GROUP = "entari_plugin_htmlrender.providers"

PLAYWRIGHT_PROVIDER_ID: Final[EngineId] = "playwright"
TAKUMI_PROVIDER_ID: Final[EngineId] = "takumi"

RESERVED_PROVIDER_IDS: frozenset[EngineId] = frozenset(
    {PLAYWRIGHT_PROVIDER_ID, TAKUMI_PROVIDER_ID}
)
_ENGINE_ID_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")

__all__ = [
    "ENTRY_POINT_GROUP",
    "PLAYWRIGHT_PROVIDER_ID",
    "RESERVED_PROVIDER_IDS",
    "TAKUMI_PROVIDER_ID",
    "EngineBindings",
    "EngineId",
    "EngineProvider",
    "ProviderAvailability",
    "ProviderDependencies",
    "ResourceStrategy",
    "validate_engine_id",
]


def validate_engine_id(value: object) -> EngineId:
    """Validate the stable identifier shared by config and entry points."""
    if not isinstance(value, str) or _ENGINE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(
            "provider id must be a non-empty lowercase identifier containing "
            "only ASCII letters, digits, '.', '_' or '-', with an alphanumeric "
            "first and last character"
        )
    return value


@dataclass(frozen=True, slots=True)
class ProviderAvailability:
    """Whether a provider can run in the current environment."""

    available: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderDependencies:
    """Services the composition root hands to ``EngineProvider.compose``.

    Providers never read global configuration or construct their own
    observers; everything they need arrives here.
    """

    operation_observer: OperationObserver
    operation_admission: OperationAdmission
    cache_observer: CacheObserver
    resources: ProviderResources
    asset_publisher: AssetPublisher | None


@dataclass(frozen=True, slots=True)
class EngineBindings:
    """Immutable composition DTO produced by ``EngineProvider.compose``.

    Only the composition root consumes this; caller code receives the
    contained lifecycle and executor through constructor injection.
    """

    lifecycle: RuntimeLifecycle
    prepared_html_executor: PreparedHtmlExecutor | None = None
    provider_capabilities: CapabilityCatalog | None = None


@runtime_checkable
class EngineProvider(Protocol[SettingsT]):
    """A render engine packaged for discovery and composition."""

    @property
    def id(self) -> EngineId: ...

    def parse_settings(self, raw: Mapping[str, object]) -> SettingsT: ...

    def availability(self, settings: SettingsT) -> ProviderAvailability: ...

    def resource_strategy(self, settings: SettingsT) -> ResourceStrategy: ...

    def compose(
        self,
        settings: SettingsT,
        dependencies: ProviderDependencies,
    ) -> EngineBindings: ...
