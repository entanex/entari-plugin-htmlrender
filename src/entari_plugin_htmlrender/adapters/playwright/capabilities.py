"""Typed Playwright page capability resolved at the composition boundary."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, final
from typing_extensions import Unpack

from entari_plugin_htmlrender.rendering.observers import observe_operation

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from playwright.async_api import Browser, Page

    from entari_plugin_htmlrender.adapters._lease import ExecutionLeaseProvider
    from entari_plugin_htmlrender.adapters.playwright.render import PlaywrightLease
    from entari_plugin_htmlrender.capabilities.playwright import PlaywrightPageOptions
    from entari_plugin_htmlrender.rendering.ports import (
        OperationAdmission,
        OperationObserver,
    )

_OBSERVATION_ATTRIBUTES = {
    "render.backend": "playwright",
    "render.access": "native",
}
_LEASE_BROWSER_OPERATION = "playwright.lease_browser"
_LEASE_PAGE_OPERATION = "playwright.lease_page"


@final
class PlaywrightCapabilityAdapter:
    """Lease raw Playwright pages or the provider-owned native browser."""

    def __init__(
        self,
        leases: ExecutionLeaseProvider[PlaywrightLease],
        observer: OperationObserver,
        *,
        operation_admission: OperationAdmission,
    ) -> None:
        self._leases = leases
        self._observer = observer
        self._operation_admission = operation_admission

    @asynccontextmanager
    async def lease_page(
        self,
        **options: Unpack[PlaywrightPageOptions],
    ) -> AsyncIterator[Page]:
        """Open a caller-controlled page bound to the leased browser."""
        async with self._operation_admission.operation(_LEASE_PAGE_OPERATION):
            from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
                PageContext,
            )

            with observe_operation(
                self._observer,
                "playwright.native.page",
                _OBSERVATION_ATTRIBUTES,
            ):
                async with (
                    self._leases.lease() as lease,
                    PageContext(lease).open(**options) as page,
                ):
                    yield page

    @asynccontextmanager
    async def lease_browser(self) -> AsyncIterator[Browser]:
        """Lease the provider-owned native browser without proxying it."""
        async with self._operation_admission.operation(_LEASE_BROWSER_OPERATION):
            from playwright.async_api import Browser  # noqa: PLC0415

            with observe_operation(
                self._observer,
                "playwright.native.browser",
                _OBSERVATION_ATTRIBUTES,
            ):
                async with self._leases.lease() as lease:
                    browser = lease.browser
                    if not isinstance(browser, Browser):
                        raise RuntimeError(
                            "Playwright lease does not expose a Browser."
                        )
                    yield browser


__all__ = ["PlaywrightCapabilityAdapter"]
