"""Managed Takumi session implementation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, TypeVar
from typing_extensions import Unpack

from entari_plugin_htmlrender.capabilities.takumi import (
    FileCachePolicy,
    GenericFontFamily,
    ImageInput,
    TakumiCacheStats,
    TakumiRasterOptions,
    TakumiSvgOptions,
)
from entari_plugin_htmlrender.errors import (
    HtmlRenderError,
    InvalidRenderInputError,
    ProviderExecutionError,
    ResourceFetchError,
    UnsupportedDocumentFeatureError,
)
from entari_plugin_htmlrender.preparation import PreparedHtml, parse_html
from entari_plugin_htmlrender.providers.sdk import TAKUMI_PROVIDER_ID
from entari_plugin_htmlrender.rendering.observers import (
    NoopOperationObserver,
    observe_operation,
)

from .errors import (
    TakumiBackendError,
    TakumiInputError,
    TakumiResourceError,
    TakumiRuntimeError,
    TakumiUnsupportedError,
)
from .operations import render_prepared_html
from .runtime import TakumiRuntimeState, render_defaults
from .source import materialize_takumi_document
from .types import TakumiImageResource

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from pathlib import Path
    from types import CoroutineType

    from entari_plugin_htmlrender.rendering.ports import OperationObserver

P = ParamSpec("P")
R = TypeVar("R")
_PROVIDER_ID = str(TAKUMI_PROVIDER_ID)


@contextmanager
def _translate_managed_error(operation: str) -> Iterator[None]:
    """Keep native Takumi failures behind the managed capability boundary."""
    try:
        yield
    except HtmlRenderError:
        raise
    except TakumiUnsupportedError as error:
        raise UnsupportedDocumentFeatureError(
            operation,
            error.feature,
            provider_id=_PROVIDER_ID,
        ) from error
    except TakumiInputError as error:
        raise InvalidRenderInputError(
            "Takumi rejected managed capability input.",
            operation=operation,
            field=error.field,
            source=error,
        ) from error
    except TakumiResourceError as error:
        raise ResourceFetchError(
            "Takumi could not materialize a managed capability resource.",
            reference=error.reference,
            operation=operation,
            source=error,
        ) from error
    except TypeError as error:
        raise InvalidRenderInputError(
            "Takumi rejected managed capability input.",
            operation=operation,
            source=error,
        ) from error
    except TakumiBackendError as error:
        raise ProviderExecutionError(
            "Takumi managed capability operation failed.",
            provider_id=_PROVIDER_ID,
            operation=operation,
            source=error,
        ) from error
    except Exception as error:
        raise ProviderExecutionError(
            "Takumi managed capability operation failed.",
            provider_id=_PROVIDER_ID,
            operation=operation,
            source=error,
        ) from error


def _tracked(
    telemetry_operation: str,
    *,
    error_operation: str,
) -> Callable[
    [Callable[Concatenate[TakumiSessionAdapter, P], CoroutineType[Any, Any, R]]],
    Callable[Concatenate[TakumiSessionAdapter, P], CoroutineType[Any, Any, R]],
]:
    def _decorate(
        func: Callable[
            Concatenate[TakumiSessionAdapter, P],
            CoroutineType[Any, Any, R],
        ],
    ) -> Callable[
        Concatenate[TakumiSessionAdapter, P],
        CoroutineType[Any, Any, R],
    ]:
        @wraps(func)
        async def _wrapped(
            session: TakumiSessionAdapter,
            /,
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> R:
            with (
                observe_operation(
                    session._observer,
                    telemetry_operation,
                    {"render.backend": "takumi"},
                ),
                _translate_managed_error(error_operation),
            ):
                session._state._ensure_open()
                return await func(session, *args, **kwargs)

        return _wrapped

    return _decorate


def _expect_svg(value: object) -> str:
    if not isinstance(value, str):
        raise TakumiRuntimeError(
            f"Takumi returned {type(value).__name__}, expected str."
        )
    return value


@dataclass(frozen=True, slots=True)
class TakumiSessionAdapter:
    """Managed provider session without native node or compiled-object leakage."""

    _state: TakumiRuntimeState
    _observer: OperationObserver = field(
        default_factory=NoopOperationObserver,
        repr=False,
        compare=False,
    )

    @property
    def registered_font_families(self) -> tuple[str, ...]:
        with _translate_managed_error("takumi.registered_font_families"):
            self._state._ensure_open()
            return self._state.registered_font_families

    @property
    def compiled_cache_stats(self) -> TakumiCacheStats:
        with _translate_managed_error("takumi.compiled_cache_stats"):
            self._state._ensure_open()
            return self._state.compiled_cache_stats

    @staticmethod
    def _prepared(html: str | PreparedHtml, base_url: str | None) -> PreparedHtml:
        if isinstance(html, PreparedHtml):
            return html
        return parse_html(html, base_url=base_url)

    @_tracked(
        "takumi.session.render_html",
        error_operation="takumi.render_html",
    )
    async def render_html(
        self,
        html: str | PreparedHtml,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        base_url: str | None = None,
        **options: Unpack[TakumiRasterOptions],
    ) -> bytes:
        return await render_prepared_html(
            self._state,
            self._prepared(html, base_url),
            stylesheets=stylesheets,
            images=images,
            width=options.get("width", 1200),
            height=options.get("height"),
            image_format=options.get("format", "png"),
            quality=options.get("quality"),
            lossless=options.get("lossless"),
            font_size=options.get("font_size", 16.0),
            device_pixel_ratio=options.get("device_pixel_ratio", 1.0),
            draw_debug_border=options.get("draw_debug_border", False),
            time_ms=options.get("time_ms", 0),
            dithering=options.get("dithering", "none"),
            lang=options.get("lang"),
            font_families=options.get("font_families"),
            keyframes=options.get("keyframes"),
        )

    @_tracked(
        "takumi.session.render_svg_html",
        error_operation="takumi.render_svg_html",
    )
    async def render_svg_html(
        self,
        html: str | PreparedHtml,
        *,
        stylesheets: Sequence[str] = (),
        images: Sequence[ImageInput] | None = None,
        base_url: str | None = None,
        **options: Unpack[TakumiSvgOptions],
    ) -> str:
        document = await materialize_takumi_document(
            self._prepared(html, base_url),
            resources=self._state.resources,
            stylesheets=stylesheets,
            images=images,
        )
        native = render_defaults(self._state, images=document.images)
        native.update(
            width=options.get("width", 1200),
            height=options.get("height", 630),
            font_size=options.get("font_size", 16.0),
            time_ms=options.get("time_ms", 0),
        )
        for key in ("keyframes", "lang"):
            value = options.get(key)
            if value is not None:
                native[key] = value
        font_families = options.get("font_families")
        if font_families is not None:
            native["font_families"] = tuple(font_families)
        rendered = await self._state.call_document(
            "render_svg_compiled",
            document.html,
            document.stylesheets,
            **native,
        )
        return _expect_svg(rendered)

    @_tracked(
        "takumi.session.register_font_file",
        error_operation="takumi.register_font_file",
    )
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
    ) -> tuple[str, ...]:
        return await self._state.register_font_file(
            path,
            name=name,
            weight=weight,
            style=style,
            subset_of=subset_of,
            generic_family=generic_family,
            cache_policy=cache_policy,
        )


__all__ = ["TakumiImageResource", "TakumiSessionAdapter"]
