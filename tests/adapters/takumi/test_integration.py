from __future__ import annotations

import pytest

from entari_plugin_htmlrender.adapters.takumi import TakumiConfig
from entari_plugin_htmlrender.adapters.takumi.api import TakumiSessionAdapter
from entari_plugin_htmlrender.adapters.takumi.runtime import create_runtime_state
from tests.adapters.takumi.helpers import resource_service


async def test_takumi_native_provider_emits_managed_png() -> None:
    pytest.importorskip("takumi_py")
    state = await create_runtime_state(TakumiConfig(), resources=resource_service())
    try:
        rendered = await TakumiSessionAdapter(state).render_html(
            '<div style="width:32px;height:16px;background:#00f"></div>',
            width=32,
            height=16,
        )
    finally:
        await state.aclose()

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
