from __future__ import annotations

from typing import TYPE_CHECKING, Any

from entari_plugin_htmlrender.runtime import resolve_runtime

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from entari_plugin_htmlrender.resources.models import ResourceResolution
    from entari_plugin_htmlrender.resources.service import ResolverSpec
    from entari_plugin_htmlrender.runtime import RuntimeSource


async def resolve_template_vars(
    template_vars: Mapping[str, Any],
    *,
    template_base: str | Path | None = None,
    strict: bool | None = None,
    resolver: ResolverSpec = None,
    runtime: RuntimeSource | None = None,
) -> ResourceResolution[dict[str, Any]]:
    return await resolve_runtime(runtime).resources.resolve_template_vars(
        template_vars,
        template_base=template_base,
        strict=strict,
        resolver=resolver,
    )


async def resolve_resource_url(
    value: str | Path | bytes,
    *,
    template_base: str | Path | None = None,
    strict: bool | None = None,
    resolver: ResolverSpec = None,
    runtime: RuntimeSource | None = None,
) -> ResourceResolution[str]:
    return await resolve_runtime(runtime).resources.resolve_resource_url(
        value,
        template_base=template_base,
        strict=strict,
        resolver=resolver,
    )


__all__ = ["resolve_resource_url", "resolve_template_vars"]
