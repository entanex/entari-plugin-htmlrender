"""Typed capability keys and the read-only capability catalog.

Provider-specific capabilities are resolved only at API/composition
boundaries via ``CapabilityKey``; runtime and domain code receive the
resolved objects through constructor injection instead.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Generic, TypeVar, final
from typing_extensions import TypeIs

from entari_plugin_htmlrender.errors import (
    CapabilityUnavailableError,
    InvalidRenderInputError,
)

T = TypeVar("T")
_CAPABILITY_NAME_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")


def _matches_interface(value: object, key: CapabilityKey[T]) -> TypeIs[T]:
    try:
        return isinstance(value, key.interface)
    except TypeError as error:
        raise TypeError(
            f"Capability `{key.name}` interface must be a concrete class, ABC, "
            "or @runtime_checkable Protocol."
        ) from error


@dataclass(frozen=True, slots=True)
class CapabilityKey(Generic[T]):
    """Typed token identifying one boundary capability."""

    name: str
    interface: type[T]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or _CAPABILITY_NAME_PATTERN.fullmatch(self.name) is None
        ):
            raise InvalidRenderInputError(
                "Capability name must be a non-empty lowercase stable identifier.",
                operation="capability.key.create",
                field="name",
            )
        if not isinstance(self.interface, type):
            raise InvalidRenderInputError(
                "Capability interface must be a runtime-checkable type.",
                operation="capability.key.create",
                field="interface",
            )
        try:
            isinstance(None, self.interface)
        except TypeError as error:
            raise InvalidRenderInputError(
                "Capability interface must support runtime isinstance checks.",
                operation="capability.key.create",
                field="interface",
                source=error,
            ) from error


@final
class CapabilityCatalog:
    """Immutable name-to-capability mapping built at composition time."""

    __slots__ = ("_values",)

    def __init__(self) -> None:
        self._values: dict[str, object] = {}

    def with_capability(self, key: CapabilityKey[T], value: T) -> CapabilityCatalog:
        """Return a new catalog that additionally exposes ``value``."""
        if key.name in self._values:
            raise ValueError(f"Capability `{key.name}` is already registered.")
        if not _matches_interface(value, key):
            raise TypeError(
                f"Capability `{key.name}` expects {key.interface.__qualname__}, "
                f"got {type(value).__qualname__}."
            )
        catalog = CapabilityCatalog()
        catalog._values = {**self._values, key.name: value}
        return catalog

    def merged(self, other: CapabilityCatalog) -> CapabilityCatalog:
        """Return the disjoint union of two already validated catalogs."""
        duplicates = self._values.keys() & other._values.keys()
        if duplicates:
            names = ", ".join(sorted(duplicates))
            raise ValueError(f"Capabilities are already registered: {names}.")
        catalog = CapabilityCatalog()
        catalog._values = {**self._values, **other._values}
        return catalog

    def get(self, key: CapabilityKey[T]) -> T | None:
        # The name is validated against the registering key's interface, but a
        # different key can share that name with an incompatible interface, so
        # the querying key's interface is re-verified before narrowing.
        value = self._values.get(key.name)
        if value is None:
            return None
        if not _matches_interface(value, key):
            raise CapabilityUnavailableError(
                key.name,
                detail=(
                    f"Registered value is {type(value).__qualname__}, "
                    f"not {key.interface.__qualname__}."
                ),
            )
        return value

    def require(self, key: CapabilityKey[T]) -> T:
        value = self.get(key)
        if value is None:
            raise CapabilityUnavailableError(key.name)
        return value

    def names(self) -> frozenset[str]:
        return frozenset(self._values)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, CapabilityKey):
            return False
        value = self._values.get(key.name)
        return value is not None and _matches_interface(value, key)
