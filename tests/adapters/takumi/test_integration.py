from __future__ import annotations

import struct

import pytest

from entari_plugin_htmlrender.adapters.takumi import TakumiConfig, TakumiRuntimeError
from entari_plugin_htmlrender.adapters.takumi.api import TakumiSessionAdapter
from entari_plugin_htmlrender.adapters.takumi.runtime import create_runtime_state
from tests.adapters.takumi.helpers import resource_service

takumi_py = pytest.importorskip("takumi_py")


async def test_takumi_native_boundary_renders_extension_output() -> None:
    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    try:
        rendered = await TakumiSessionAdapter(state).render_html(
            '<div style="width:32px;height:16px;background:#00f"></div>',
            width=32,
            height=16,
            device_pixel_ratio=2,
        )
    finally:
        await state.aclose()

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", rendered[16:24]) == (64, 32)


async def test_native_methods_are_not_projected_onto_the_managed_session() -> None:
    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    try:
        session = TakumiSessionAdapter(state)
        assert not hasattr(session, "compile_node")
        assert not hasattr(session, "compile_keyframes")
    finally:
        await state.aclose()


async def test_takumi_native_error_is_translated_at_runtime_boundary() -> None:
    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    try:
        with pytest.raises(TakumiRuntimeError, match="compile") as raised:
            await state.compile_stylesheet("}", lossy=False)
    finally:
        await state.aclose()

    assert isinstance(raised.value.__cause__, takumi_py.StyleSheetError)
