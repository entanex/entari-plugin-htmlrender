from __future__ import annotations

import inspect
from typing import get_type_hints

from entari_plugin_htmlrender.adapters.takumi.advanced import TakumiAPIAdapter
from entari_plugin_htmlrender.capabilities import (
    TakumiAPI,
    TakumiCapability,
    TakumiSession,
)
from entari_plugin_htmlrender.capabilities.takumi import ImageInput

SESSION_METHODS = {
    "register_font_file",
    "render_html",
    "render_svg_html",
}
ADVANCED_METHODS = {
    "compile_html",
    "compile_keyframes",
    "compile_node",
    "compile_stylesheet",
    "encode_frames",
    "measure_compiled",
    "measure_html",
    "measure_node",
    "render_animation",
    "render_compiled",
    "render_html",
    "render_node",
    "render_sequence_at_time",
    "render_svg_compiled",
    "render_svg_html",
    "render_svg_node",
    "register_font",
    "register_font_file",
    "register_fonts",
}
ADVANCED_PROPERTIES = {
    "compiled_cache_stats",
    "registered_font_families",
}


def test_managed_takumi_session_is_small_async_and_native_free() -> None:
    methods = {
        name
        for name, value in vars(TakumiSession).items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == SESSION_METHODS
    assert (ADVANCED_METHODS - SESSION_METHODS).isdisjoint(vars(TakumiSession))
    assert all(
        inspect.iscoroutinefunction(getattr(TakumiSession, name)) for name in methods
    )


def test_advanced_takumi_api_exposes_the_complete_explicit_surface() -> None:
    methods = {
        name
        for name, value in vars(TakumiAPI).items()
        if callable(value) and not name.startswith("_")
    }
    properties = {
        name for name, value in vars(TakumiAPI).items() if isinstance(value, property)
    }

    assert methods == ADVANCED_METHODS
    assert properties == ADVANCED_PROPERTIES
    assert all(
        inspect.iscoroutinefunction(getattr(TakumiAPI, name)) for name in methods
    )


def test_advanced_takumi_adapter_implements_the_protocol_surface() -> None:
    methods = {
        name
        for name, value in vars(TakumiAPIAdapter).items()
        if callable(value) and not name.startswith("_")
    }
    properties = {
        name
        for name, value in vars(TakumiAPIAdapter).items()
        if isinstance(value, property)
    }

    assert methods == ADVANCED_METHODS
    assert properties == ADVANCED_PROPERTIES
    assert all(
        inspect.iscoroutinefunction(getattr(TakumiAPIAdapter, name)) for name in methods
    )


def test_takumi_protocol_annotations_are_runtime_resolvable() -> None:
    assert ImageInput is not object
    for name in SESSION_METHODS:
        assert get_type_hints(getattr(TakumiSession, name))
    for name in ADVANCED_METHODS:
        assert get_type_hints(getattr(TakumiAPI, name))
    assert get_type_hints(TakumiCapability.lease_session)
    assert get_type_hints(TakumiCapability.lease_api)
    assert get_type_hints(TakumiCapability.lease_native_renderer)


def test_every_takumi_access_mode_is_explicitly_leased() -> None:
    assert "lease_session" in vars(TakumiCapability)
    assert "lease_api" in vars(TakumiCapability)
    assert "lease_native_renderer" in vars(TakumiCapability)
    assert "api" not in vars(TakumiCapability)
    assert "renderer" not in vars(TakumiCapability)
