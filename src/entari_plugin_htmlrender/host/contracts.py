"""Stable caller-facing contracts for Entari-owned render services."""

from typing import Protocol

from entari_plugin_htmlrender.runtime import RuntimeResolver

from .config import RenderSettings


class HtmlRenderService(RuntimeResolver, Protocol):
    """Service surface injected into Entari handlers.

    The host owns the concrete Launart component. Callers depend only on
    synchronous runtime resolution, detached settings, and explicit close.
    """

    @property
    def settings(self) -> RenderSettings: ...

    async def aclose(self) -> None: ...


__all__ = ["HtmlRenderService"]
