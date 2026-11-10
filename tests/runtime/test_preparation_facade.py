"""Provider-free preparation and the retained facade's shutdown contract."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import anyio
import anyio.lowlevel
import pytest

from entari_plugin_htmlrender import HtmlPreparer, PreparedHtml, TemplateRef, parse_html
from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    RuntimeUnavailableError,
)
from entari_plugin_htmlrender.resources import FileResourceRef
from entari_plugin_htmlrender.runtime import RuntimeState
from entari_plugin_htmlrender.runtime.preparation import _AdmittedHtmlPreparer

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from entari_plugin_htmlrender.resources import ResourceRef
    from entari_plugin_htmlrender.resources.templating import (
        ExtensionSpec,
        FilterCallable,
    )


async def test_prepare_without_backend_returns_reusable_documents(
    tmp_path: Path,
) -> None:
    (tmp_path / "card.html").write_text("<p>{{ title }}</p>")
    runtime = build_runtime_plan(
        HtmlRenderConfig.model_validate(
            {"resources": {"local_access": {"allowed_paths": [tmp_path]}}}
        )
    ).build_runtime()
    preparation = runtime.preparation
    assert isinstance(preparation, HtmlPreparer)
    try:
        text = await preparation.prepare_text("<script>unsafe</script>")
        assert "&lt;script&gt;unsafe&lt;/script&gt;" in text.html
        markdown = await preparation.prepare_markdown("# Hello\n\n**Entari**")
        assert "<h1>Hello</h1>" in markdown.html
        assert "<strong>Entari</strong>" in markdown.html
        template = TemplateRef(tmp_path, "card.html")
        prepared = await preparation.prepare_template(template, {"title": "Entari"})
        assert "<p>Entari</p>" in prepared.html
        assert prepared.document_base.resolve() == tmp_path.as_uri() + "/"
        assert await preparation.render_template(template, {"title": "HTML"}) == (
            "<p>HTML</p>"
        )
        html = await preparation.prepare_html(
            "<p>raw</p>", base_url="https://example.com/"
        )
        assert html.document_base.resolve() == "https://example.com/"
        assert not runtime.renderer.supported_operations
    finally:
        await runtime.aclose()

    calls = [
        preparation.prepare_html("<p>closed</p>"),
        preparation.prepare_text("closed"),
        preparation.prepare_markdown("closed"),
        preparation.prepare_template(template, {}),
        preparation.render_template(template, {}),
    ]
    for call in calls:
        with pytest.raises(RuntimeUnavailableError) as captured:
            await call
        assert captured.value.state == "closed"
        assert captured.value.operation is not None
        assert captured.value.operation.startswith("preparation.")


async def test_close_waits_for_preparation_before_releasing_resources() -> None:
    runtime = build_runtime_plan(HtmlRenderConfig()).build_runtime()
    entered = anyio.Event()
    release = anyio.Event()

    class WaitingPreparer:
        async def prepare_text(
            self, text: str, *, stylesheet: ResourceRef | None = None
        ) -> PreparedHtml:
            del stylesheet
            entered.set()
            await release.wait()
            return parse_html(text)

    preparation = _AdmittedHtmlPreparer(
        cast("HtmlPreparer", WaitingPreparer()), runtime._operation_admission
    )
    async with anyio.create_task_group() as group:
        group.start_soon(preparation.prepare_text, "in flight")
        await entered.wait()
        group.start_soon(runtime.aclose)
        while runtime.state is RuntimeState.OPEN:
            await anyio.lowlevel.checkpoint()
        assert runtime.state is RuntimeState.CLOSING
        with pytest.raises(RuntimeUnavailableError):
            await preparation.prepare_text("new operation")
        release.set()
    assert runtime.state is RuntimeState.CLOSED


async def test_preparation_validates_inputs_before_resource_io() -> None:
    runtime = build_runtime_plan(HtmlRenderConfig()).build_runtime()
    preparation = runtime.preparation
    try:
        calls = [
            preparation.prepare_html(cast("str", object())),
            preparation.prepare_html("x", base_url=cast("str", 123)),
            preparation.prepare_text(cast("str", object())),
            preparation.prepare_text("x", stylesheet=cast("ResourceRef", object())),
            preparation.prepare_markdown(cast("str", object())),
            preparation.prepare_template(cast("TemplateRef", object()), {}),
            preparation.render_template(cast("TemplateRef", object()), {}),
            preparation.prepare_template(
                TemplateRef(Path.cwd(), "unused.html"),
                cast("Mapping[str, object]", {1: "bad key"}),
            ),
            preparation.prepare_template(
                TemplateRef(Path.cwd(), "unused.html"),
                {},
                filters=cast("Mapping[str, FilterCallable]", {"bad": 1}),
            ),
            preparation.render_template(
                TemplateRef(Path.cwd(), "unused.html"),
                {},
                extensions=cast("Sequence[ExtensionSpec]", "jinja2.ext.do"),
            ),
            preparation.render_template(
                TemplateRef(Path.cwd(), "unused.html"),
                {},
                extensions=cast("Sequence[ExtensionSpec]", (object(),)),
            ),
        ]
        for call in calls:
            with pytest.raises(InvalidRenderInputError):
                await call
        # Validation failures release admission and never poison future preparation.
        result = await preparation.prepare_markdown("still **open**")
        assert "<strong>open</strong>" in result.html
    finally:
        await runtime.aclose()


async def test_preparation_reuses_authorized_file_resources(tmp_path: Path) -> None:
    source = tmp_path / "content.md"
    source.write_text("# From a file")
    runtime = build_runtime_plan(
        HtmlRenderConfig.model_validate(
            {"resources": {"local_access": {"allowed_paths": [tmp_path]}}}
        )
    ).build_runtime()
    try:
        result = await runtime.preparation.prepare_markdown(FileResourceRef(source))
        assert "<h1>From a file</h1>" in result.html
    finally:
        await runtime.aclose()


async def test_template_customizations_work_through_each_public_facade(
    tmp_path: Path,
) -> None:
    template = TemplateRef(tmp_path, "card.html")
    (tmp_path / "card.html").write_text(
        "{% set labels = [] %}{% do labels.append(title | badge) %}"
        "<p>{{ labels[0] }}</p>"
    )
    runtime = build_runtime_plan(
        HtmlRenderConfig.model_validate(
            {"resources": {"local_access": {"allowed_paths": [tmp_path]}}}
        )
    ).build_runtime()

    def badge(value: str) -> str:
        return f"<{value.upper()}>"

    try:
        options = {"badge": badge}
        expected = "<p>&lt;ENTARI&gt;</p>"
        html = await runtime.templates.render(
            template,
            {"title": "Entari"},
            filters=options,
            extensions=("jinja2.ext.do",),
        )
        assert html.content == expected
        prepared = await runtime.preparation.prepare_template(
            template,
            {"title": "Entari"},
            filters=options,
            extensions=("jinja2.ext.do",),
        )
        assert prepared.html == expected
        assert (
            await runtime.preparation.render_template(
                template,
                {"title": "Entari"},
                filters=options,
                extensions=("jinja2.ext.do",),
            )
            == expected
        )
        # A new callable must create a separate cached environment.
        other = await runtime.templates.render(
            template,
            {"title": "Entari"},
            filters={"badge": str.lower},
            extensions=("jinja2.ext.do",),
        )
        assert other.content == "<p>entari</p>"
    finally:
        await runtime.aclose()
