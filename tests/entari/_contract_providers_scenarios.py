"""Isolated regression for the plugin's ownership of registration waits."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from entari_plugin_htmlrender.entari import providers
from entari_plugin_htmlrender.entari.service import HtmlRenderService
from entari_plugin_htmlrender.resources import ResourceAccess


async def _main() -> None:
    registered: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    entered = asyncio.Event()
    wait_calls = 0
    component: SimpleNamespace | None = None

    async def wait_for(service_id: str) -> None:
        nonlocal wait_calls
        assert service_id == HtmlRenderService.id
        wait_calls += 1
        entered.set()
        await registered

    def get_component(service_id: str) -> SimpleNamespace:
        assert service_id == HtmlRenderService.id
        if component is None:
            raise ValueError(service_id)
        return component

    manager = SimpleNamespace(get_component=get_component)
    plugin = SimpleNamespace(module=SimpleNamespace(), is_available=True)
    service = SimpleNamespace(service_waiter=SimpleNamespace(wait_for=wait_for))
    with patch.multiple(
        providers,
        it=lambda _: manager,
        find_plugin=lambda _: plugin,
        plugin_service=service,
    ):
        provider = providers._ContractProvider(ResourceAccess)
        callers = [asyncio.create_task(provider._active_service()) for _ in range(3)]
        await asyncio.wait_for(entered.wait(), timeout=1)
        for caller in callers[:2]:
            caller.cancel()
        cancelled = await asyncio.wait_for(
            asyncio.gather(*callers[:2], return_exceptions=True), timeout=1
        )
        assert all(isinstance(result, asyncio.CancelledError) for result in cancelled)
        assert not registered.done()
        assert not callers[2].done()
        assert wait_calls == 1

        component = SimpleNamespace(status=SimpleNamespace(stage="prepared"))
        registered.set_result(None)
        assert await asyncio.wait_for(callers[2], timeout=1) is component
        await asyncio.sleep(0)
        assert provider._registration_task is None


if __name__ == "__main__":
    asyncio.run(_main())
