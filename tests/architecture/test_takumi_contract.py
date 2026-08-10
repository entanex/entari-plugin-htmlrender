from __future__ import annotations

import inspect
from typing import get_type_hints

from entari_plugin_htmlrender.capabilities import TakumiCapability, TakumiSession
from entari_plugin_htmlrender.capabilities.takumi import ImageInput

MANAGED_METHODS = {
    "register_font_file",
    "render_html",
    "render_svg_html",
}
NATIVE_ONLY_METHODS = {
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
    "render_node",
    "render_sequence_at_time",
    "render_svg_compiled",
    "render_svg_node",
}


def test_managed_takumi_session_is_small_async_and_native_free() -> None:
    methods = {
        name
        for name, value in vars(TakumiSession).items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == MANAGED_METHODS
    assert NATIVE_ONLY_METHODS.isdisjoint(vars(TakumiSession))
    assert all(
        inspect.iscoroutinefunction(getattr(TakumiSession, name)) for name in methods
    )


def test_takumi_protocol_annotations_are_runtime_resolvable() -> None:
    assert ImageInput is not object
    for name in MANAGED_METHODS:
        assert get_type_hints(getattr(TakumiSession, name))
    assert get_type_hints(TakumiCapability.lease_session)
    assert get_type_hints(TakumiCapability.lease_native_renderer)


def test_native_access_is_explicitly_leased() -> None:
    assert "lease_session" in vars(TakumiCapability)
    assert "lease_native_renderer" in vars(TakumiCapability)
    assert "api" not in vars(TakumiCapability)
    assert "renderer" not in vars(TakumiCapability)
