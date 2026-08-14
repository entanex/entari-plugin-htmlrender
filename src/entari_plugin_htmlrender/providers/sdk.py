"""Provider SDK: stable contracts for render-provider composition.

A provider is loaded either from an explicit composition-root override or
from the versioned ``entari_plugin_htmlrender.providers.v2`` entry-point group.
Raw mappings cross the boundary once through :meth:`RenderProvider.parse_config`;
the resulting provider-owned value flows unchanged through availability,
resource planning, and composition.
"""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003 -- runtime annotation contract
from dataclasses import dataclass
import re
from typing import Final, NewType, TypeAlias, TypeVar
from typing_extensions import Protocol, runtime_checkable

from entari_plugin_htmlrender.rendering.capabilities import (  # noqa: TC001
    CapabilityCatalog,
)
from entari_plugin_htmlrender.rendering.ports import (  # noqa: TC001
    OperationAdmission,
    OperationObserver,
    PreparedHtmlExecutor,
    RuntimeLifecycle,
)
from entari_plugin_htmlrender.resources.config import (
    LocalResourceStrategy,
    RemoteResourceStrategy,
    ResourceStrategy,
)
from entari_plugin_htmlrender.resources.observation import (  # noqa: TC001
    CacheObserver,
)
from entari_plugin_htmlrender.resources.ports import (  # noqa: TC001
    AssetPublisher,
    ProviderResourceAccess,
)

ProviderId = NewType("ProviderId", str)
ConfigT = TypeVar("ConfigT")

ENTRY_POINT_GROUP = "entari_plugin_htmlrender.providers.v2"

PLAYWRIGHT_PROVIDER_ID: Final[ProviderId] = ProviderId("playwright")
TAKUMI_PROVIDER_ID: Final[ProviderId] = ProviderId("takumi")

RESERVED_PROVIDER_IDS: frozenset[ProviderId] = frozenset(
    {PLAYWRIGHT_PROVIDER_ID, TAKUMI_PROVIDER_ID}
)
_PROVIDER_ID_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")

__all__ = [
    "ENTRY_POINT_GROUP",
    "PLAYWRIGHT_PROVIDER_ID",
    "RESERVED_PROVIDER_IDS",
    "TAKUMI_PROVIDER_ID",
    "LocalResourceStrategy",
    "ProviderAvailability",
    "ProviderAvailable",
    "ProviderBinding",
    "ProviderDependencies",
    "ProviderId",
    "ProviderUnavailable",
    "RemoteResourceStrategy",
    "RenderProvider",
    "ResourceStrategy",
    "validate_provider_id",
]


def validate_provider_id(value: object) -> ProviderId:
    """Validate the stable identifier shared by config and entry points."""
    if not isinstance(value, str) or _PROVIDER_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(
            "provider id must be a non-empty lowercase identifier containing "
            "only ASCII letters, digits, '.', '_' or '-', with an alphanumeric "
            "first and last character"
        )
    return ProviderId(value)


@dataclass(frozen=True, slots=True)
class ProviderAvailable:
    """The provider can run with the parsed configuration."""


@dataclass(frozen=True, slots=True)
class ProviderUnavailable:
    """The provider cannot currently run with the parsed configuration."""

    reason: str
    retryable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("provider unavailability reason must not be empty")
        if type(self.retryable) is not bool:
            raise ValueError("provider unavailability retryable must be a boolean")


ProviderAvailability: TypeAlias = ProviderAvailable | ProviderUnavailable


@dataclass(frozen=True, slots=True)
class ProviderDependencies:
    """Services the composition root hands to ``RenderProvider.compose``.

    Providers never read global configuration or construct their own
    observers; everything they need arrives here.
    """

    operation_observer: OperationObserver
    operation_admission: OperationAdmission
    cache_observer: CacheObserver
    resources: ProviderResourceAccess
    asset_publisher: AssetPublisher | None


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    """Immutable composition value produced by ``RenderProvider.compose``.

    Only the composition root consumes this; caller code receives the
    contained lifecycle and executor through constructor injection.
    """

    lifecycle: RuntimeLifecycle
    prepared_html_executor: PreparedHtmlExecutor | None = None
    provider_capabilities: CapabilityCatalog | None = None


@runtime_checkable
class RenderProvider(Protocol[ConfigT]):
    """A discoverable implementation of HTML rendering operations."""

    @property
    def id(self) -> ProviderId: ...

    def parse_config(self, raw: Mapping[str, object]) -> ConfigT: ...

    def check_availability(self, config: ConfigT) -> ProviderAvailability: ...

    def resource_strategy(self, config: ConfigT) -> ResourceStrategy: ...

    def compose(
        self,
        config: ConfigT,
        dependencies: ProviderDependencies,
    ) -> ProviderBinding: ...
