"""Page context lifecycle and network helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, final
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from urllib.request import url2pathname

import anyio
from playwright.async_api import Browser, Page, Route

from entari_plugin_htmlrender._logging import logger
from entari_plugin_htmlrender.preparation.references import rewrite_css_references
from entari_plugin_htmlrender.resources.errors import (
    ResourceAccessDeniedError,
    ResourceError,
    ResourceFetchError,
)
from entari_plugin_htmlrender.resources.headers import merge_request_headers
from entari_plugin_htmlrender.resources.models import (
    FileResourceRef,
    PublishedResource,
    RemoteResourceRef,
    ResourceContent,
)

from .telemetry import detach_page, instrument_page

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from playwright.async_api import WebSocketRoute

    from entari_plugin_htmlrender.resources.ports import ProviderResourceAccess

    from .render import PlaywrightLease


class _ConsoleEvent(Protocol):
    @property
    def type(self) -> str: ...


class _RequestEvent(Protocol):
    @property
    def method(self) -> str: ...

    @property
    def resource_type(self) -> str: ...


class _ResponseEvent(Protocol):
    @property
    def status(self) -> int: ...

    @property
    def request(self) -> _RequestEvent: ...


@final
class PageContext:
    """Open and instrument pages from one injected Playwright lease."""

    def __init__(self, lease: PlaywrightLease) -> None:
        self._lease = lease

    @asynccontextmanager
    async def open(self, **kwargs: Any) -> AsyncIterator[Page]:
        browser = self._lease.browser
        if not isinstance(browser, Browser):
            raise RuntimeError("Playwright lease does not expose a Browser.")
        page = await browser.new_page(**kwargs)
        instrument_page(page, page_name="render_context")
        try:
            yield page
        finally:
            try:
                with anyio.CancelScope(shield=True):
                    await page.close()
            finally:
                detach_page(page)


def log_console_event(message: _ConsoleEvent) -> None:
    """Log only the console event type; console text is untrusted payload."""
    logger.debug(f"Browser console event: type={message.type}")


def log_page_error_event(_error: object) -> None:
    """Log a page error without its message, which is untrusted payload."""
    logger.warning("Page raised an uncaught error.")


def log_request_failed_event(request: _RequestEvent) -> None:
    """Log only stable request fields; the URL is untrusted payload."""
    logger.warning(
        "Playwright request failed: "
        f"method={request.method}, resource_type={request.resource_type}"
    )


def log_response_event(response: _ResponseEvent) -> None:
    """Log only the status and resource type for failed image/document loads."""
    if response.status >= 400 and response.request.resource_type in {
        "image",
        "document",
    }:
        logger.warning(
            "Playwright response error: "
            f"status={response.status}, "
            f"resource_type={response.request.resource_type}"
        )


def _setup_page_logging(page: Page) -> None:
    """Log only stable page events; page content is untrusted.

    Console text, page-error messages, request URLs and Playwright failure
    detail can all carry attacker-controlled payload, so only the stable
    event type, HTTP method, resource type and status code are recorded.
    """
    page.on("console", log_console_event)
    page.on("pageerror", log_page_error_event)
    page.on("requestfailed", log_request_failed_event)
    page.on("response", log_response_event)


def _normalize_request_url(url: str) -> str:
    """Canonical identity for matching a request against published URLs.

    Mirrors the publisher-side normalization: scheme/host case, default port
    and fragment only. Path and query stay significant, so a different query
    or a redirect target never matches another resource's authorization.
    """
    split = urlsplit(url)
    scheme = split.scheme.lower()
    host = (split.hostname or "").lower()
    default_port = {"http": 80, "https": 443}.get(scheme)
    port = split.port
    netloc = host if port is None or port == default_port else f"{host}:{port}"
    return urlunsplit((scheme, netloc, split.path, split.query, ""))


def _file_url_path(url: str) -> Path:
    split = urlsplit(url)
    if split.netloc not in {"", "localhost"}:
        raise ResourceAccessDeniedError(
            "Remote file URL authorities are not allowed.",
            reference=url,
            operation="fetch",
        )
    return Path(url2pathname(split.path)).expanduser()


@final
class ManagedRequestGuard:
    """Route every managed browser request through policy-bound resources."""

    def __init__(
        self,
        resources: ProviderResourceAccess,
        *,
        authorization: Mapping[str, Mapping[str, str]],
        preset_request_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._resources = resources
        self._authorization = authorization
        self._preset_request_headers = dict(preset_request_headers or {})
        self._failure: ResourceError | None = None

    def raise_if_failed(self) -> None:
        """Surface the first route failure after Playwright handles an abort."""
        if self._failure is not None:
            raise self._failure

    def _record_failure(self, error: BaseException) -> None:
        if self._failure is not None:
            return
        if isinstance(error, ResourceError):
            self._failure = error
            return
        self._failure = ResourceFetchError(
            "A managed browser resource could not be fetched.",
            reference=None,
            operation="fetch",
            source=error,
        )

    async def install(self, page: Page) -> None:
        """Install the managed HTTP(S) guard and block WebSocket upgrades."""
        # Imports use an isolated browser.new_page context, so a context-level
        # catch-all also covers popups, frames, and dedicated workers. Narrow
        # page routes for immutable in-memory assets still take precedence.
        await page.context.route("**/*", self._handle_route)
        await page.context.route_web_socket("**/*", self._reject_web_socket)

    async def _handle_route(self, route: Route) -> None:
        request = route.request
        try:
            if request.method.upper() != "GET":
                raise ResourceAccessDeniedError(
                    "Managed browser renders only allow GET requests.",
                    reference=request.url,
                    operation="fetch",
                )
            split = urlsplit(request.url)
            if split.scheme in {"http", "https"}:
                publication_headers = self._authorization.get(
                    _normalize_request_url(request.url)
                )
                request_headers = merge_request_headers(
                    self._preset_request_headers,
                    publication_headers or {},
                )
                if publication_headers is not None or request_headers:
                    content = await self._resources.fetch_published(
                        PublishedResource(request.url, request_headers)
                    )
                else:
                    content = await self._resources.fetch(
                        RemoteResourceRef(request.url)
                    )
            elif split.scheme == "file":
                content = await self._resources.fetch(
                    FileResourceRef(_file_url_path(request.url))
                )
            else:
                raise ResourceAccessDeniedError(
                    "Managed browser requests require http, https, or file.",
                    reference=request.url,
                    operation="fetch",
                )
            await self._fulfill(route, request.url, content)
        except ResourceError as error:
            self._record_failure(error)
            await route.abort(error_code="blockedbyclient")
            return
        except Exception as error:
            self._record_failure(error)
            await route.abort(error_code="failed")
            return
        except BaseException:
            await route.abort(error_code="aborted")
            raise

    async def _fulfill(
        self,
        route: Route,
        request_url: str,
        content: ResourceContent,
    ) -> None:
        """Fulfil one fetched resource without allowing browser fallback."""
        body = content.data
        if content.final_url is not None and content.media_type == "text/css":
            final_url = content.final_url
            try:
                css = body.decode("utf-8-sig")
            except UnicodeDecodeError:
                pass
            else:

                def resolve_css_reference(reference: str) -> str:
                    resolved, fragment = urldefrag(urljoin(final_url, reference))
                    return f"{resolved}#{fragment}" if fragment else resolved

                body = rewrite_css_references(
                    css,
                    resolve_css_reference,
                ).encode()
        elif content.final_url is not None and content.media_type in {
            "text/html",
            "application/xhtml+xml",
        }:
            raise ResourceFetchError(
                "Redirected HTML cannot be fulfilled safely in a managed render.",
                reference=request_url,
                operation="fetch",
            )
        await route.fulfill(
            status=200,
            body=body,
            content_type=content.media_type or "application/octet-stream",
            headers={"access-control-allow-origin": "*"},
        )

    async def _reject_web_socket(self, socket: WebSocketRoute) -> None:
        self._record_failure(
            ResourceAccessDeniedError(
                "Managed browser renders do not allow WebSocket connections.",
                reference=socket.url,
                operation="fetch",
            )
        )
        await socket.close(code=1008, reason="WebSocket access is blocked")


__all__ = [
    "ManagedRequestGuard",
    "PageContext",
]
