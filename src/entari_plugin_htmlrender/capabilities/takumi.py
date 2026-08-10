"""Stable managed capability for Takumi-specific operations.

The managed session deliberately does not mirror Takumi's native node,
compiled-document, measurement, frame, or animation surface. Callers that
need those implementation-specific objects must opt into
``lease_native_renderer()`` and own the native typing themselves.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import (  # noqa: TC003 -- public hints
    AbstractAsyncContextManager,
)
from dataclasses import dataclass
from enum import Enum
from pathlib import Path  # noqa: TC003 -- public hints
from typing import Literal, Protocol, runtime_checkable
from typing_extensions import TypeAlias, TypedDict, Unpack

from entari_plugin_htmlrender.preparation.models import (  # noqa: TC001 -- public hints
    PreparedHtml,
)
from entari_plugin_htmlrender.rendering.capabilities import CapabilityKey

ImageCacheMode: TypeAlias = Literal["auto", "none"]
StaticImageFormat: TypeAlias = Literal["png", "jpeg", "jpg", "webp", "ico", "raw"]
DitheringAlgorithm: TypeAlias = Literal[
    "none",
    "ordered-bayer",
    "floyd-steinberg",
]
TakumiKeyframesInput: TypeAlias = (
    Mapping[str, Mapping[str, Mapping[str, str | int | float]]]
    | Sequence[Mapping[str, object]]
)
GenericFontFamily: TypeAlias = Literal[
    "serif",
    "sans-serif",
    "monospace",
    "cursive",
    "fantasy",
    "system-ui",
    "ui-serif",
    "ui-sans-serif",
    "ui-monospace",
    "ui-rounded",
    "emoji",
    "math",
    "fangsong",
]


class FileCachePolicy(str, Enum):
    """Validation policy for user-provided Takumi font files."""

    IMMUTABLE = "immutable"
    REVALIDATE = "revalidate"


@dataclass(frozen=True, slots=True)
class TakumiImageResource:
    """An image made available under an exact HTML/CSS source key."""

    src: str
    data: bytes
    cache: ImageCacheMode = "auto"


class TakumiImageResourceLike(Protocol):
    """Promised image duck type accepted without importing Takumi."""

    src: str
    data: bytes


TakumiImageInput: TypeAlias = (
    TakumiImageResource | tuple[str, bytes] | TakumiImageResourceLike
)
ImageInput: TypeAlias = TakumiImageInput


class TakumiCacheStats(Protocol):
    """Read-only snapshot of the runtime's compiled-document cache."""

    @property
    def entries(self) -> int: ...

    @property
    def resident_weight(self) -> int: ...

    @property
    def hits(self) -> int: ...

    @property
    def misses(self) -> int: ...

    @property
    def loads(self) -> int: ...

    @property
    def waits(self) -> int: ...

    @property
    def evictions(self) -> int: ...


class TakumiRasterOptions(TypedDict, total=False):
    """Stable raster options for ``TakumiSession.render_html``."""

    width: int | None
    height: int | None
    format: StaticImageFormat
    quality: int | None
    lossless: bool | None
    font_size: float
    device_pixel_ratio: float
    draw_debug_border: bool
    time_ms: int
    dithering: DitheringAlgorithm
    keyframes: TakumiKeyframesInput | None
    font_families: Sequence[str] | None
    lang: str | None


class TakumiSvgOptions(TypedDict, total=False):
    """Stable vector options for ``TakumiSession.render_svg_html``."""

    width: int | None
    height: int | None
    font_size: float
    time_ms: int
    keyframes: TakumiKeyframesInput | None
    font_families: Sequence[str] | None
    lang: str | None


class TakumiSession(Protocol):
    """Managed Takumi operations valid for one leased runtime session."""

    @property
    def registered_font_families(self) -> tuple[str, ...]: ...

    @property
    def compiled_cache_stats(self) -> TakumiCacheStats: ...

    async def render_html(
        self,
        html: str | PreparedHtml,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        base_url: str | None = None,
        **options: Unpack[TakumiRasterOptions],
    ) -> bytes: ...

    async def render_svg_html(
        self,
        html: str | PreparedHtml,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        base_url: str | None = None,
        **options: Unpack[TakumiSvgOptions],
    ) -> str: ...

    async def register_font_file(
        self,
        path: str | Path,
        *,
        name: str | None = None,
        weight: float | None = None,
        style: str | None = None,
        subset_of: str | None = None,
        generic_family: GenericFontFamily | None = None,
        cache_policy: FileCachePolicy = FileCachePolicy.REVALIDATE,
    ) -> tuple[str, ...]: ...


@runtime_checkable
class TakumiCapability(Protocol):
    """Lease the managed session or explicitly opt into the native renderer."""

    def lease_session(self) -> AbstractAsyncContextManager[TakumiSession]: ...

    def lease_native_renderer(self) -> AbstractAsyncContextManager[object]: ...


TAKUMI: CapabilityKey[TakumiCapability] = CapabilityKey(
    "takumi",
    TakumiCapability,
)

__all__ = [
    "TAKUMI",
    "DitheringAlgorithm",
    "FileCachePolicy",
    "GenericFontFamily",
    "ImageCacheMode",
    "ImageInput",
    "StaticImageFormat",
    "TakumiCacheStats",
    "TakumiCapability",
    "TakumiImageInput",
    "TakumiImageResource",
    "TakumiImageResourceLike",
    "TakumiKeyframesInput",
    "TakumiRasterOptions",
    "TakumiSession",
    "TakumiSvgOptions",
]
