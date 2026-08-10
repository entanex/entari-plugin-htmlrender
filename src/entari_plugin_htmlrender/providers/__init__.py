"""Stable provider contracts and versioned discovery."""

from .discovery import resolve_provider as resolve_provider
from .sdk import ENTRY_POINT_GROUP as ENTRY_POINT_GROUP
from .sdk import PLAYWRIGHT_PROVIDER_ID as PLAYWRIGHT_PROVIDER_ID
from .sdk import RESERVED_PROVIDER_IDS as RESERVED_PROVIDER_IDS
from .sdk import TAKUMI_PROVIDER_ID as TAKUMI_PROVIDER_ID
from .sdk import LocalResourceStrategy as LocalResourceStrategy
from .sdk import ProviderAvailability as ProviderAvailability
from .sdk import ProviderAvailable as ProviderAvailable
from .sdk import ProviderBinding as ProviderBinding
from .sdk import ProviderDependencies as ProviderDependencies
from .sdk import ProviderId as ProviderId
from .sdk import ProviderUnavailable as ProviderUnavailable
from .sdk import RemoteResourceStrategy as RemoteResourceStrategy
from .sdk import RenderProvider as RenderProvider
from .sdk import ResourceStrategy as ResourceStrategy

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
    "resolve_provider",
]
