"""Provider resolution: explicit overrides, first-party ids, entry points.

Only the provider selected by configuration is ever imported. Explicit
providers passed to the composition root take precedence (tests, embedding);
``playwright`` and ``takumi`` are reserved for the first-party
adapters and cannot be overridden through entry points.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import entry_points
from typing import Any, cast

from entari_plugin_htmlrender.errors import (
    ProviderConfigurationError,
    ProviderConflictError,
    ProviderNotFoundError,
    ProviderSelectionError,
)

from .sdk import (
    ENTRY_POINT_GROUP,
    PLAYWRIGHT_PROVIDER_ID,
    RESERVED_PROVIDER_IDS,
    TAKUMI_PROVIDER_ID,
    ProviderId,
    RenderProvider,
    validate_provider_id,
)

_FIRST_PARTY_MODULES: dict[str, str] = {
    PLAYWRIGHT_PROVIDER_ID: "entari_plugin_htmlrender.adapters.playwright.provider",
    TAKUMI_PROVIDER_ID: "entari_plugin_htmlrender.adapters.takumi.provider",
}
_FIRST_PARTY_ATTRIBUTE = "PROVIDER"


def _validate_provider(
    candidate: object,
    *,
    origin: str,
    expected_provider_id: ProviderId | None = None,
) -> tuple[RenderProvider[Any], ProviderId]:
    try:
        conforms = isinstance(candidate, RenderProvider)
    except Exception as error:
        raise ProviderSelectionError(
            f"Could not inspect the provider object from {origin}.",
            provider_id=(
                None if expected_provider_id is None else str(expected_provider_id)
            ),
            operation="inspect_provider",
            source=error,
        ) from error
    if not conforms:
        raise ProviderSelectionError(
            f"Object from {origin} does not implement the RenderProvider "
            f"protocol: {candidate!r}.",
            provider_id=(
                None if expected_provider_id is None else str(expected_provider_id)
            ),
            operation="resolve_provider",
        )
    provider = cast("RenderProvider[Any]", candidate)
    try:
        candidate_id = provider.id
    except Exception as error:
        raise ProviderSelectionError(
            f"Could not read the provider id from {origin}.",
            provider_id=(
                None if expected_provider_id is None else str(expected_provider_id)
            ),
            operation="inspect_provider_id",
            source=error,
        ) from error
    try:
        validated_id = validate_provider_id(candidate_id)
    except ValueError as error:
        raise ProviderConfigurationError(
            f"Object from {origin} declares an invalid provider id: {candidate_id!r}.",
            provider_id=str(candidate_id),
            operation="validate_provider_id",
            source=error,
        ) from error
    return provider, validated_id


def _load_first_party(provider_id: ProviderId) -> RenderProvider[Any]:
    try:
        module = import_module(_FIRST_PARTY_MODULES[provider_id])
        candidate = getattr(module, _FIRST_PARTY_ATTRIBUTE)
    except Exception as error:
        raise ProviderSelectionError(
            f"Could not import the first-party provider {provider_id!r}.",
            provider_id=str(provider_id),
            operation="import_first_party_provider",
            source=error,
        ) from error
    provider, actual_id = _validate_provider(
        candidate,
        origin=f"first-party module for `{provider_id}`",
        expected_provider_id=provider_id,
    )
    if actual_id != provider_id:
        raise ProviderConfigurationError(
            f"First-party provider {provider_id!r} declares mismatched id "
            f"{actual_id!r}.",
            provider_id=str(provider_id),
            operation="resolve_provider",
        )
    return provider


def _load_entry_point(provider_id: ProviderId) -> RenderProvider[Any]:
    matches = [
        entry_point
        for entry_point in entry_points(group=ENTRY_POINT_GROUP)
        if entry_point.name == provider_id
    ]
    if not matches:
        raise ProviderNotFoundError(
            f"No provider named {provider_id!r} is installed. Install a package "
            f"exposing it through the {ENTRY_POINT_GROUP!r} entry-point group, "
            "or pass an explicit provider to the composition root.",
            provider_id=str(provider_id),
            operation="resolve_provider",
        )
    if len(matches) > 1:
        distributions = ", ".join(str(entry_point.dist) for entry_point in matches)
        raise ProviderConflictError(
            f"Multiple entry points register provider id {provider_id!r} "
            f"({distributions}); uninstall the conflicting distributions.",
            provider_id=str(provider_id),
            operation="resolve_provider",
        )

    try:
        loaded = matches[0].load()
    except Exception as error:
        raise ProviderSelectionError(
            f"Could not load the entry point for provider {provider_id!r}.",
            provider_id=str(provider_id),
            operation="load_provider_entry_point",
            source=error,
        ) from error
    if isinstance(loaded, type):
        try:
            candidate = loaded()
        except Exception as error:
            raise ProviderSelectionError(
                f"Could not construct the provider from entry point {provider_id!r}.",
                provider_id=str(provider_id),
                operation="construct_provider",
                source=error,
            ) from error
    else:
        candidate = loaded
    provider, actual_id = _validate_provider(
        candidate,
        origin=f"entry point {provider_id!r}",
        expected_provider_id=provider_id,
    )
    if actual_id != provider_id:
        raise ProviderConfigurationError(
            f"Entry point {provider_id!r} resolved to a provider with "
            f"mismatched id {actual_id!r}.",
            provider_id=str(provider_id),
            operation="resolve_provider",
        )
    return provider


def _reject_reserved_hijack(provider_id: ProviderId) -> None:
    hijackers = [
        entry_point
        for entry_point in entry_points(group=ENTRY_POINT_GROUP)
        if entry_point.name == provider_id
    ]
    if hijackers:
        distributions = ", ".join(str(entry_point.dist) for entry_point in hijackers)
        raise ProviderConflictError(
            f"Provider id {provider_id!r} is reserved for the first-party "
            f"adapter and cannot be overridden by entry points "
            f"({distributions}).",
            provider_id=str(provider_id),
            operation="resolve_provider",
        )


def resolve_provider(
    provider_id: ProviderId,
    *,
    provider_override: RenderProvider[Any] | None = None,
) -> RenderProvider[Any]:
    """Resolve the configured provider without importing any other engine."""
    try:
        provider_id = validate_provider_id(provider_id)
    except ValueError as error:
        raise ProviderConfigurationError(
            f"Configured provider id {provider_id!r} is invalid.",
            provider_id=str(provider_id),
            operation="validate_provider_id",
            source=error,
        ) from error
    if provider_override is not None:
        provider, override_id = _validate_provider(
            provider_override,
            origin="explicit override",
            expected_provider_id=provider_id,
        )
        if override_id != provider_id:
            raise ProviderConfigurationError(
                f"Explicit provider override for {provider_id!r} declares "
                f"mismatched id {override_id!r}.",
                provider_id=str(provider_id),
                operation="resolve_provider",
            )
        return provider

    if provider_id in RESERVED_PROVIDER_IDS:
        _reject_reserved_hijack(provider_id)
        return _load_first_party(provider_id)

    return _load_entry_point(provider_id)


__all__ = ["resolve_provider"]
