"""Typed keys for independently composed raster-scene backends."""

from __future__ import annotations

from entari_plugin_htmlrender.rendering.capabilities import CapabilityKey

from .ports import GraphicsRenderer

PILLOW_RASTER_SCENE_RENDERER: CapabilityKey[GraphicsRenderer] = CapabilityKey(
    "graphics.pillow.raster_scene_renderer",
    GraphicsRenderer,
)
SKIA_RASTER_SCENE_RENDERER: CapabilityKey[GraphicsRenderer] = CapabilityKey(
    "graphics.skia.raster_scene_renderer",
    GraphicsRenderer,
)

__all__ = [
    "PILLOW_RASTER_SCENE_RENDERER",
    "SKIA_RASTER_SCENE_RENDERER",
]
