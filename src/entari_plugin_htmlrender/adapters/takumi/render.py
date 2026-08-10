from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from typing import TYPE_CHECKING, final

from entari_plugin_htmlrender.adapters.takumi.errors import TakumiRuntimeError
from entari_plugin_htmlrender.adapters.takumi.runtime import (
    create_runtime_state,
    require_runtime_state,
)
from entari_plugin_htmlrender.providers.sdk import (
    TAKUMI_PROVIDER_ID,
    ProviderAvailability,
    ProviderAvailable,
    ProviderUnavailable,
)
from entari_plugin_htmlrender.rendering.observers import observe_operation

if TYPE_CHECKING:
    from entari_plugin_htmlrender.rendering.ports import OperationObserver
    from entari_plugin_htmlrender.resources.observation import CacheObserver
    from entari_plugin_htmlrender.resources.ports import ProviderResourceAccess

    from .config import TakumiConfig
    from .runtime import TakumiRuntimeState

_SUPPORTED_TAKUMI_VERSION = "0.2.0"
OBSERVATION_ATTRIBUTES: dict[str, str] = {"render.backend": TAKUMI_PROVIDER_ID}


@final
class TakumiEngine:
    """Own one native Takumi runtime using injected settings and observers."""

    def __init__(
        self,
        *,
        config: TakumiConfig,
        operation_observer: OperationObserver,
        cache_observer: CacheObserver,
        resources: ProviderResourceAccess,
    ) -> None:
        self._config = config
        self._operation_observer = operation_observer
        self._cache_observer = cache_observer
        self._resources = resources

    async def create_lease(self) -> TakumiRuntimeState:
        with observe_operation(
            self._operation_observer,
            "takumi.open_runtime",
            OBSERVATION_ATTRIBUTES,
        ):
            return await create_runtime_state(
                self._config,
                resources=self._resources,
                cache_observer=self._cache_observer,
            )

    def is_alive(self, state: TakumiRuntimeState) -> bool:
        try:
            require_runtime_state(state)
        except TakumiRuntimeError:
            return False
        return state.healthy

    async def close_lease(self, state: TakumiRuntimeState) -> None:
        with observe_operation(
            self._operation_observer,
            "takumi.close_runtime",
            OBSERVATION_ATTRIBUTES,
        ):
            await state.aclose()


def takumi_availability() -> ProviderAvailability:
    try:
        if find_spec("takumi_py") is None:
            return ProviderUnavailable(
                reason="Optional dependency `takumi-py==0.2.0` is not installed.",
            )
    except (ImportError, ValueError) as error:
        return ProviderUnavailable(
            reason=f"Cannot locate takumi_py: {error}",
        )

    try:
        installed_version = version("takumi-py")
    except PackageNotFoundError:
        return ProviderUnavailable(
            reason="Distribution metadata for `takumi-py` is unavailable.",
        )
    if installed_version != _SUPPORTED_TAKUMI_VERSION:
        return ProviderUnavailable(
            reason=(
                f"Unsupported takumi-py version {installed_version!r}; "
                f"expected {_SUPPORTED_TAKUMI_VERSION!r}."
            ),
        )

    return ProviderAvailable()


__all__ = ["OBSERVATION_ATTRIBUTES", "TakumiEngine", "takumi_availability"]
