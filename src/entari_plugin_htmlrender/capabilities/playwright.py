"""Stable capability for scoped access to provider-owned Playwright objects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence  # noqa: TC003 -- public hints
from contextlib import (  # noqa: TC003 -- public hints
    AbstractAsyncContextManager,
)
from pathlib import Path  # noqa: TC003 -- public hints
from re import Pattern  # noqa: TC003 -- public hints
from typing import Any, Literal, Protocol, runtime_checkable
from typing_extensions import TypedDict, Unpack

from entari_plugin_htmlrender.rendering.capabilities import CapabilityKey


class PlaywrightPageOptions(TypedDict, total=False):
    """Stable options accepted when leasing a new native Playwright page."""

    viewport: Mapping[str, int] | None
    screen: Mapping[str, int] | None
    no_viewport: bool | None
    ignore_https_errors: bool | None
    java_script_enabled: bool | None
    bypass_csp: bool | None
    user_agent: str | None
    locale: str | None
    timezone_id: str | None
    geolocation: Mapping[str, float] | None
    permissions: Sequence[str] | None
    extra_http_headers: Mapping[str, str] | None
    offline: bool | None
    http_credentials: Mapping[str, object] | None
    device_scale_factor: float | None
    is_mobile: bool | None
    has_touch: bool | None
    color_scheme: Literal["dark", "light", "no-preference", "null"] | None
    forced_colors: Literal["active", "none", "null"] | None
    contrast: Literal["more", "no-preference", "null"] | None
    reduced_motion: Literal["no-preference", "null", "reduce"] | None
    accept_downloads: bool | None
    default_browser_type: str | None
    proxy: Mapping[str, object] | None
    record_har_path: Path | str | None
    record_har_omit_content: bool | None
    record_video_dir: Path | str | None
    record_video_size: Mapping[str, int] | None
    storage_state: Mapping[str, object] | Path | str | None
    base_url: str | None
    strict_selectors: bool | None
    service_workers: Literal["allow", "block"] | None
    record_har_url_filter: Pattern[str] | str | None
    record_har_mode: Literal["full", "minimal"] | None
    record_har_content: Literal["attach", "embed", "omit"] | None
    client_certificates: Sequence[Mapping[str, object]] | None


@runtime_checkable
class PlaywrightCapability(Protocol):
    """Lease native Playwright objects within runtime-owned lifetimes.

    Native objects intentionally have type ``Any`` because Playwright is an
    optional dependency. The stable contract owns the lease and option shape;
    projects that install Playwright retain its native typing at adapter call
    sites without importing it during base-package startup.
    """

    def lease_page(
        self,
        **options: Unpack[PlaywrightPageOptions],
    ) -> AbstractAsyncContextManager[Any]: ...

    def lease_browser(self) -> AbstractAsyncContextManager[Any]: ...


PLAYWRIGHT: CapabilityKey[PlaywrightCapability] = CapabilityKey(
    "playwright",
    PlaywrightCapability,
)

__all__ = [
    "PLAYWRIGHT",
    "PlaywrightCapability",
    "PlaywrightPageOptions",
]
