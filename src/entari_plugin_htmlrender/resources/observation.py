from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, final

from entari_plugin_htmlrender._logging import logger

if TYPE_CHECKING:
    from collections.abc import Mapping


class CacheObserver(Protocol):
    def record(
        self,
        cache: str,
        events: Mapping[str, int],
        entries: int,
        resident_bytes: int | None = None,
    ) -> None: ...


@final
class NoopCacheObserver:
    def record(
        self,
        cache: str,
        events: Mapping[str, int],
        entries: int,
        resident_bytes: int | None = None,
    ) -> None:
        del cache, events, entries, resident_bytes


def record_cache_observation(
    observer: CacheObserver,
    cache: str,
    events: Mapping[str, int],
    entries: int,
    resident_bytes: int | None = None,
) -> None:
    try:
        observer.record(cache, events, entries, resident_bytes)
    except Exception as error:
        logger.warning("Cache observer failed for %s: %s", cache, error)


__all__ = ["CacheObserver", "NoopCacheObserver", "record_cache_observation"]
