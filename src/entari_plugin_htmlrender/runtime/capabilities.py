"""Typed capabilities exposed by one composed render runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, final

from entari_plugin_htmlrender.capabilities import (
    PLAYWRIGHT,
    TAKUMI,
    PlaywrightCapability,
    TakumiCapability,
)

if TYPE_CHECKING:
    from entari_plugin_htmlrender.rendering.capabilities import (
        CapabilityCatalog,
        CapabilityKey,
    )

T = TypeVar("T")


@final
class RuntimeCapabilities:
    """Read-only typed access to optional capabilities in one composition."""

    __slots__ = ("_catalog",)

    def __init__(self, catalog: CapabilityCatalog) -> None:
        self._catalog = catalog

    @property
    def playwright(self) -> PlaywrightCapability:
        return self._catalog.require(PLAYWRIGHT)

    @property
    def takumi(self) -> TakumiCapability:
        return self._catalog.require(TAKUMI)

    @property
    def available_names(self) -> frozenset[str]:
        """Return the stable names present in this immutable composition."""
        return self._catalog.names()

    def get(self, key: CapabilityKey[T]) -> T | None:
        """Return an optional third-party capability by its typed key."""
        return self._catalog.get(key)

    def require(self, key: CapabilityKey[T]) -> T:
        """Return a required third-party capability or raise a typed error."""
        return self._catalog.require(key)

    def __contains__(self, key: object) -> bool:
        return key in self._catalog


__all__ = ["RuntimeCapabilities"]
