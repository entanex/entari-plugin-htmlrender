"""Stable managed capabilities for Takumi-specific operations.

``TakumiSession`` is the small caller-facing rendering surface.
``TakumiAPI`` mirrors Takumi's compiled-document, node, measurement, SVG,
animation, and font operations for callers that explicitly opt into the
provider-specific contract. ``lease_native_renderer()`` remains available for
the unmanaged upstream object.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import (  # noqa: TC003 -- public hints
    AbstractAsyncContextManager,
)
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path  # noqa: TC003 -- public hints
import threading
from typing import TYPE_CHECKING, Any, Literal, Protocol, final, runtime_checkable
from typing_extensions import TypeAlias, TypedDict, Unpack

from entari_plugin_htmlrender._typing import (
    identity_decorator,
    project_method_parameters,
)
from entari_plugin_htmlrender.errors import RuntimeUnavailableError
from entari_plugin_htmlrender.preparation.models import (  # noqa: TC001 -- public hints
    PreparedHtml,
)
from entari_plugin_htmlrender.rendering.capabilities import CapabilityKey

if TYPE_CHECKING:
    from takumi_py import AnimationScene as NativeAnimationScene
    from takumi_py import CompiledNode as NativeCompiledNode
    from takumi_py import CompiledStyleSheet as NativeCompiledStyleSheet
    from takumi_py import FontResourceInput as NativeFontResourceInput
    from takumi_py import MeasuredNode as NativeMeasuredNode
    from takumi_py import NodeInput as NativeNodeInput
    from takumi_py import RawAnimationFrame as NativeRawAnimationFrame
    from takumi_py import Renderer as NativeTakumiRenderer

    _compile_node_signature = project_method_parameters(
        NativeTakumiRenderer.compile_node
    )
    _compile_keyframes_signature = project_method_parameters(
        NativeTakumiRenderer.compile_keyframes
    )
else:
    NativeAnimationScene = object
    NativeCompiledNode = object
    NativeCompiledStyleSheet = object
    NativeFontResourceInput = object
    NativeMeasuredNode = object
    NativeNodeInput = object
    NativeRawAnimationFrame = object
    NativeTakumiRenderer = object
    _compile_node_signature = identity_decorator
    _compile_keyframes_signature = identity_decorator

ImageCacheMode: TypeAlias = Literal["auto", "none"]
StaticImageFormat: TypeAlias = Literal["png", "jpeg", "jpg", "webp", "ico", "raw"]
AnimationImageFormat: TypeAlias = Literal["webp", "apng", "gif"]
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


class FileCachePolicy(StrEnum):
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


class TakumiMeasureOptions(TypedDict, total=False):
    """Layout-measurement options shared by the HTML, node, and document APIs."""

    width: int | None
    height: int | None
    font_size: float
    device_pixel_ratio: float
    draw_debug_border: bool
    time_ms: int
    dithering: DitheringAlgorithm
    keyframes: TakumiKeyframesInput | None
    font_families: Sequence[str] | None
    lang: str | None


class TakumiFrameEncodeOptions(TypedDict, total=False):
    """Animation container options shared with ``encode_frames``."""

    format: AnimationImageFormat
    quality: int | None
    lossless: bool | None
    loop_count: int | None
    webp_blend: bool
    webp_dispose: bool
    webp_speed: int | None


class TakumiAnimationOptions(TakumiFrameEncodeOptions, total=False):
    """Scene rendering plus animation-container encoding options."""

    width: int | None
    height: int | None
    font_size: float
    device_pixel_ratio: float
    draw_debug_border: bool
    dithering: DitheringAlgorithm
    keyframes: TakumiKeyframesInput | None
    font_families: Sequence[str] | None
    lang: str | None
    fps: int


class TakumiSequenceOptions(TypedDict, total=False):
    """Static raster options for one animation timestamp."""

    width: int | None
    height: int | None
    format: StaticImageFormat
    quality: int | None
    lossless: bool | None
    font_size: float
    device_pixel_ratio: float
    draw_debug_border: bool
    dithering: DitheringAlgorithm
    keyframes: TakumiKeyframesInput | None
    font_families: Sequence[str] | None
    lang: str | None


@final
class _TakumiLeaseGuard:
    """Invalidate managed adapter objects when their capability lease exits."""

    __slots__ = ("_active", "_lock", "_runtime")

    def __init__(self, runtime: object) -> None:
        self._runtime = runtime
        self._lock = threading.Lock()
        self._active = True

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def ensure_active(self, operation: str) -> None:
        with self._lock:
            active = self._active
        if not active:
            raise RuntimeUnavailableError("lease_expired", operation=operation)

    def ensure_owned_by(self, runtime: object, operation: str) -> None:
        with self._lock:
            owned = runtime is self._runtime
        if not owned:
            raise RuntimeUnavailableError("foreign_runtime", operation=operation)

    def invalidate(self) -> None:
        with self._lock:
            self._active = False


@dataclass(frozen=True, slots=True)
class TakumiCompiledDocument:
    """Compiled HTML and stylesheets tied to one Takumi runtime."""

    node: NativeCompiledNode
    stylesheets: tuple[NativeCompiledStyleSheet, ...]
    images: tuple[ImageInput, ...] = ()
    _lease_guard: _TakumiLeaseGuard | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def _ensure_owned_by(
        self,
        runtime: object,
        lease_guard: _TakumiLeaseGuard,
        operation: str,
    ) -> None:
        if self._lease_guard is None:
            raise RuntimeUnavailableError("unleased_document", operation=operation)
        self._lease_guard.ensure_owned_by(runtime, operation)
        if self._lease_guard is not lease_guard:
            raise RuntimeUnavailableError("foreign_lease", operation=operation)
        self._lease_guard.ensure_active(operation)


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
class TakumiAPI(Protocol):
    """Complete managed Takumi API leased for the lifetime of one context."""

    @property
    def registered_font_families(self) -> tuple[str, ...]: ...

    @property
    def compiled_cache_stats(self) -> TakumiCacheStats: ...

    async def compile_html(
        self,
        html: str | PreparedHtml,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        base_url: str | None = None,
    ) -> TakumiCompiledDocument: ...

    @_compile_node_signature
    async def compile_node(self, *args: Any, **kwargs: Any) -> NativeCompiledNode: ...

    async def compile_stylesheet(
        self,
        css: str,
        *,
        lossy: bool = False,
    ) -> NativeCompiledStyleSheet: ...

    @_compile_keyframes_signature
    async def compile_keyframes(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> NativeCompiledStyleSheet: ...

    async def render_html(
        self,
        html: str | PreparedHtml,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        base_url: str | None = None,
        **options: Unpack[TakumiRasterOptions],
    ) -> bytes: ...

    async def render_compiled(
        self,
        document: TakumiCompiledDocument,
        **options: Unpack[TakumiRasterOptions],
    ) -> bytes: ...

    async def measure_html(
        self,
        html: str | PreparedHtml,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        base_url: str | None = None,
        **options: Unpack[TakumiMeasureOptions],
    ) -> NativeMeasuredNode: ...

    async def measure_compiled(
        self,
        document: TakumiCompiledDocument,
        **options: Unpack[TakumiMeasureOptions],
    ) -> NativeMeasuredNode: ...

    async def render_svg_html(
        self,
        html: str | PreparedHtml,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        base_url: str | None = None,
        **options: Unpack[TakumiSvgOptions],
    ) -> str: ...

    async def render_svg_compiled(
        self,
        document: TakumiCompiledDocument,
        **options: Unpack[TakumiSvgOptions],
    ) -> str: ...

    async def render_node(
        self,
        node: NativeNodeInput,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        validate: bool = False,
        **options: Unpack[TakumiRasterOptions],
    ) -> bytes: ...

    async def measure_node(
        self,
        node: NativeNodeInput,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        validate: bool = False,
        **options: Unpack[TakumiMeasureOptions],
    ) -> NativeMeasuredNode: ...

    async def render_svg_node(
        self,
        node: NativeNodeInput,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        validate: bool = False,
        **options: Unpack[TakumiSvgOptions],
    ) -> str: ...

    async def render_animation(
        self,
        scenes: Sequence[NativeAnimationScene],
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        validate: bool = False,
        **options: Unpack[TakumiAnimationOptions],
    ) -> bytes: ...

    async def render_sequence_at_time(
        self,
        scenes: Sequence[NativeAnimationScene],
        time_ms: int,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        validate: bool = False,
        **options: Unpack[TakumiSequenceOptions],
    ) -> bytes: ...

    async def encode_frames(
        self,
        frames: Sequence[NativeRawAnimationFrame],
        **options: Unpack[TakumiFrameEncodeOptions],
    ) -> bytes: ...

    async def register_font(
        self,
        font: NativeFontResourceInput,
        *,
        source: str | None = None,
    ) -> tuple[str, ...]: ...

    async def register_fonts(
        self,
        fonts: Sequence[NativeFontResourceInput],
        *,
        sources: Sequence[str | None] | None = None,
    ) -> tuple[str, ...]: ...

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
    """Lease the small session, advanced API, or unmanaged native renderer."""

    def lease_session(self) -> AbstractAsyncContextManager[TakumiSession]: ...

    def lease_api(self) -> AbstractAsyncContextManager[TakumiAPI]: ...

    def lease_native_renderer(
        self,
    ) -> AbstractAsyncContextManager[NativeTakumiRenderer]: ...


TAKUMI: CapabilityKey[TakumiCapability] = CapabilityKey(
    "takumi",
    TakumiCapability,
)

__all__ = [
    "TAKUMI",
    "AnimationImageFormat",
    "DitheringAlgorithm",
    "FileCachePolicy",
    "GenericFontFamily",
    "ImageCacheMode",
    "ImageInput",
    "StaticImageFormat",
    "TakumiAPI",
    "TakumiAnimationOptions",
    "TakumiCacheStats",
    "TakumiCapability",
    "TakumiCompiledDocument",
    "TakumiFrameEncodeOptions",
    "TakumiImageInput",
    "TakumiImageResource",
    "TakumiImageResourceLike",
    "TakumiKeyframesInput",
    "TakumiMeasureOptions",
    "TakumiRasterOptions",
    "TakumiSequenceOptions",
    "TakumiSession",
    "TakumiSvgOptions",
]
