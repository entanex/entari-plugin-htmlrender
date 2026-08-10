from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from entari_plugin_htmlrender import api

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from entari_plugin_htmlrender.runtime import RenderRuntime

pytestmark = pytest.mark.requires_browser

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
async def started_runtime() -> AsyncIterator[RenderRuntime]:
    runtime = api.resolve_runtime()
    await runtime.startup()
    yield runtime
    await runtime.aclose()


async def test_render_text_produces_png(
    started_runtime: RenderRuntime,
) -> None:
    assert started_runtime is api.resolve_runtime()

    artifact = await api.render_text("hello end-to-end")

    assert bytes(artifact)[: len(_PNG_MAGIC)] == _PNG_MAGIC
    assert artifact.media_type == "image/png"


async def test_render_html_and_markdown_produce_images(
    started_runtime: RenderRuntime,
) -> None:
    assert started_runtime is api.resolve_runtime()

    html_artifact = await api.render_html("<h1>e2e</h1>")
    markdown_artifact = await api.render_markdown("# e2e")

    assert bytes(html_artifact)[: len(_PNG_MAGIC)] == _PNG_MAGIC
    assert bytes(markdown_artifact)[: len(_PNG_MAGIC)] == _PNG_MAGIC
