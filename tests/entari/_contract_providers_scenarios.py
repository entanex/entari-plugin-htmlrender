from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from arclet.entari.plugin.service import ServiceWaiters

from entari_plugin_htmlrender.entari import providers
from entari_plugin_htmlrender.entari.service import HtmlRenderService
from entari_plugin_htmlrender.resources import ResourceAccess


class _TrackingServiceWaiters(ServiceWaiters):
    def __init__(self) -> None:
        super().__init__()
        self.waiting = 0
        self.changed = asyncio.Event()

    async def wait_for(self, service_id: str) -> None:
        self.waiting += 1
        self.changed.set()
        try:
            await super().wait_for(service_id)
        finally:
            self.waiting -= 1
            self.changed.set()


class _Manager:
    def __init__(self) -> None:
        self.components: dict[str, Any] = {}

    def get_component(self, service_id: str) -> Any:
        try:
            return self.components[service_id]
        except KeyError:
            raise ValueError(service_id) from None


async def _wait_until(waiters: _TrackingServiceWaiters, predicate: Any) -> None:
    async with asyncio.timeout(1):
        while not predicate():
            waiters.changed.clear()
            if not predicate():
                await waiters.changed.wait()


async def _assert_cancelled(caller: asyncio.Task[Any]) -> None:
    caller.cancel()
    try:
        await asyncio.wait_for(caller, timeout=0.2)
    except asyncio.CancelledError:
        return
    raise AssertionError("provider caller did not cancel promptly")


def _patches(
    *,
    manager: _Manager,
    waiters: _TrackingServiceWaiters,
    plugin: Any,
) -> tuple[SimpleNamespace, tuple[Any, ...]]:
    fake_service = SimpleNamespace(service_waiter=waiters)
    patches = (
        patch.object(providers, "it", lambda _: manager),
        patch.object(providers, "find_plugin", lambda _: plugin),
        patch.object(providers, "plugin_service", fake_service),
    )
    return fake_service, patches


async def _cancel_keeps_direct_waiter_pending() -> None:
    manager = _Manager()
    waiters = _TrackingServiceWaiters()
    plugin = SimpleNamespace(module=SimpleNamespace(), is_available=True)
    _, active_patches = _patches(manager=manager, waiters=waiters, plugin=plugin)
    with active_patches[0], active_patches[1], active_patches[2]:
        provider = providers._ContractProvider(ResourceAccess)
        provider_caller = asyncio.create_task(provider._active_service())
        direct_waiter = asyncio.create_task(waiters.wait_for(HtmlRenderService.id))
        await _wait_until(waiters, lambda: waiters.waiting == 2)

        await _assert_cancelled(provider_caller)
        assert not direct_waiter.done()
        assert waiters.waiting == 2

        component = SimpleNamespace(
            resources=object(),
            status=SimpleNamespace(stage="prepared"),
        )
        manager.components[HtmlRenderService.id] = component
        waiters.assign(HtmlRenderService.id)

        assert await asyncio.wait_for(direct_waiter, timeout=0.2) is None
        await _wait_until(waiters, lambda: waiters.waiting == 0)
        await asyncio.sleep(0)
        assert provider._registration_task is None
        assert await provider._active_service() is component


async def _repeated_cancellation_reuses_one_registration_task() -> None:
    manager = _Manager()
    waiters = _TrackingServiceWaiters()
    plugin = SimpleNamespace(module=SimpleNamespace(), is_available=True)
    _, active_patches = _patches(manager=manager, waiters=waiters, plugin=plugin)
    with active_patches[0], active_patches[1], active_patches[2]:
        provider = providers._ContractProvider(ResourceAccess)
        callers = [
            asyncio.create_task(provider._active_service()),
            asyncio.create_task(provider._active_service()),
            asyncio.create_task(provider._active_service()),
        ]
        await _wait_until(waiters, lambda: waiters.waiting == 1)

        for caller in callers:
            caller.cancel()
        cancelled = await asyncio.wait_for(
            asyncio.gather(*callers, return_exceptions=True),
            timeout=0.2,
        )
        assert all(isinstance(result, asyncio.CancelledError) for result in cancelled)
        registration = provider._registration_task
        assert registration is not None
        assert not registration.done()
        assert waiters.waiting == 1

        waiters.clear(HtmlRenderService.id)
        await _wait_until(waiters, lambda: waiters.waiting == 0)
        await asyncio.sleep(0)
        assert registration.done()
        assert provider._registration_task is None


async def _registration_uses_replacement_owner_waiter() -> None:
    manager = _Manager()
    waiters = _TrackingServiceWaiters()
    plugin = SimpleNamespace(module=SimpleNamespace(), is_available=True)
    fake_service, active_patches = _patches(
        manager=manager,
        waiters=waiters,
        plugin=plugin,
    )
    with active_patches[0], active_patches[1], active_patches[2]:
        provider = providers._ContractProvider(ResourceAccess)
        initial_caller = asyncio.create_task(provider._active_service())
        await _wait_until(waiters, lambda: waiters.waiting == 1)
        await _assert_cancelled(initial_caller)
        waiters.clear(HtmlRenderService.id)
        await _wait_until(waiters, lambda: waiters.waiting == 0)
        await asyncio.sleep(0)

        replacement_waiters = _TrackingServiceWaiters()
        fake_service.service_waiter = replacement_waiters
        caller = asyncio.create_task(provider._active_service())
        await _wait_until(
            replacement_waiters,
            lambda: replacement_waiters.waiting == 1,
        )

        component = SimpleNamespace(
            resources=object(),
            status=SimpleNamespace(stage="prepared"),
        )
        manager.components[HtmlRenderService.id] = component
        replacement_waiters.assign(HtmlRenderService.id)

        assert await asyncio.wait_for(caller, timeout=0.2) is component
        await _wait_until(
            replacement_waiters,
            lambda: replacement_waiters.waiting == 0,
        )


async def _prepared_service_resolves_without_waiting() -> None:
    manager = _Manager()
    waiters = _TrackingServiceWaiters()
    plugin = SimpleNamespace(module=SimpleNamespace(), is_available=True)
    component = SimpleNamespace(
        resources=object(),
        status=SimpleNamespace(stage="prepared"),
    )
    manager.components[HtmlRenderService.id] = component
    _, active_patches = _patches(manager=manager, waiters=waiters, plugin=plugin)
    with active_patches[0], active_patches[1], active_patches[2]:
        resolved = await providers._ContractProvider(ResourceAccess)._active_service()

        assert resolved is component
        assert waiters.waiting == 0
        assert HtmlRenderService.id not in waiters._futures


async def _main() -> None:
    await _cancel_keeps_direct_waiter_pending()
    await _repeated_cancellation_reuses_one_registration_task()
    await _registration_uses_replacement_owner_waiter()
    await _prepared_service_resolves_without_waiting()


if __name__ == "__main__":
    asyncio.run(_main())
