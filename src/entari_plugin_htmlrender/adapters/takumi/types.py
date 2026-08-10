from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeAlias

from entari_plugin_htmlrender.capabilities.takumi import (
    ImageCacheMode as ImageCacheMode,
)
from entari_plugin_htmlrender.capabilities.takumi import (
    StaticImageFormat as StaticImageFormat,
)
from entari_plugin_htmlrender.capabilities.takumi import (
    TakumiImageInput as TakumiImageInput,
)
from entari_plugin_htmlrender.capabilities.takumi import (
    TakumiImageResource as TakumiImageResource,
)
from entari_plugin_htmlrender.capabilities.takumi import (
    TakumiImageResourceLike as TakumiImageResourceLike,
)

AnimationImageFormat: TypeAlias = Literal["webp", "apng", "gif"]

if TYPE_CHECKING:
    from takumi_py import CompiledHtml, Renderer

    NativeCompiledHtml: TypeAlias = CompiledHtml
    NativeRenderer: TypeAlias = Renderer

__all__ = [
    "AnimationImageFormat",
    "ImageCacheMode",
    "StaticImageFormat",
    "TakumiImageInput",
    "TakumiImageResource",
    "TakumiImageResourceLike",
]
