from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import threading
from typing import TYPE_CHECKING, cast

import pytest

from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    ResourceNotFoundError,
)
from entari_plugin_htmlrender.preparation import (
    DocumentBase,
    DocumentRequirement,
    DocumentStructureSnapshot,
    PreparedAsset,
    PreparedStylesheet,
    RasterOptions,
    TemplateRef,
    parse_html,
)
from entari_plugin_htmlrender.resources.models import FileResourceRef

if TYPE_CHECKING:
    from typing import Any, Literal

    from entari_plugin_htmlrender.preparation.models import PreparedHtml
    from entari_plugin_htmlrender.preparation.service import DefaultHtmlPreparer


def test_parse_html_preserves_document_and_extracts_css() -> None:
    prepared = parse_html(
        "<style>.card { color: red }</style><main class='card'>ok</main>",
        stylesheets=[".logo { background: url(https://cdn.example/logo.png) }"],
        assets=[PreparedAsset("memory://icon", b"icon", "image/png")],
    )
    assert [stylesheet.embedded for stylesheet in prepared.stylesheets] == [False, True]
    assert prepared.assets[0].source == "memory://icon"
    assert DocumentRequirement.NETWORK in prepared.requirements


def test_parse_html_detects_script_and_local_resources() -> None:
    prepared = parse_html('<script>run()</script><img src="./avatar.png">')
    assert prepared.requirements == frozenset(
        {DocumentRequirement.JAVASCRIPT, DocumentRequirement.LOCAL_RESOURCE}
    )


def test_parse_html_captures_declared_base_href_semantics() -> None:
    prepared = parse_html(
        '<base href="assets/"><img src="a.png">',
        base_url="https://cdn.example/cards/card.html",
    )
    # declared_href is captured verbatim; resolution against the preparation
    # base happens lazily.
    assert prepared.document_base.declared_href == "assets/"
    assert prepared.document_base.resolve() == "https://cdn.example/cards/assets/"


def test_document_base_relative_href_resolves_against_execution_fallback() -> None:
    # No preparation base URL, but a relative <base href> and an
    # execution-time fallback document URL: resolve() combines them.
    prepared = parse_html('<base href="assets/"><img src="a.png">')
    assert prepared.document_base.preparation_base_url is None
    resolved = prepared.document_base.resolve(
        fallback_base_url="https://render.example/cards/card.html"
    )
    assert resolved == "https://render.example/cards/assets/"


def test_first_base_with_href_attribute_wins_even_when_empty() -> None:
    # An explicit empty href="" is a declared base distinct from an
    # undeclared one; it resolves to the document URL and a later <base>
    # must not override it.
    prepared = parse_html(
        '<base href=""><base href="late/"><img src="a.png">',
        base_url="https://example.test/cards/card.html",
    )
    assert prepared.document_base.declared_href == ""
    assert prepared.document_base.resolve() == "https://example.test/cards/card.html"

    undeclared = parse_html(
        '<img src="a.png">',
        base_url="https://example.test/cards/card.html",
    )
    assert undeclared.document_base.declared_href is None


def test_structure_snapshot_survives_dataclasses_replace() -> None:
    # Execution-time asset staging uses dataclasses.replace and must keep the
    # preparation-time parse results without re-parsing the markup.
    prepared = parse_html(
        '<base href="assets/"><img src="a.png">',
        base_url="https://cdn.example/cards/card.html",
    )
    staged = replace(prepared, assets=())
    assert staged.structure is prepared.structure
    assert staged.document_base is prepared.document_base
    assert staged.structure.references == ("a.png",)
    assert staged.structure.base_tag is not None


@pytest.mark.parametrize(
    ("html", "base_url"),
    [
        ("<img src='http://['>", None),
        ("<p>plain</p>", "http://["),
    ],
)
def test_parse_html_translates_invalid_resource_urls(
    html: str,
    base_url: str | None,
) -> None:
    with pytest.raises(InvalidRenderInputError):
        parse_html(html, base_url=base_url)


@pytest.mark.parametrize(
    ("arguments", "field"),
    [
        ({"stylesheets": (object(),)}, "stylesheets"),
        ({"assets": (object(),)}, "assets"),
    ],
)
def test_parse_html_rejects_invalid_component_types_precisely(
    arguments: dict[str, object],
    field: str,
) -> None:
    with pytest.raises(InvalidRenderInputError) as raised:
        parse_html("<p>hello</p>", **cast("Any", arguments))

    assert raised.value.operation == "html.parse"
    assert raised.value.field == field


@pytest.mark.parametrize(
    ("factory", "field"),
    [
        (lambda: PreparedAsset("", b"data"), "source"),
        (lambda: PreparedAsset("asset", cast("bytes", bytearray())), "data"),
        (lambda: PreparedAsset("asset", b"data", 'image/png" unsafe'), "media_type"),
        (lambda: PreparedStylesheet(cast("str", object())), "css"),
        (lambda: DocumentBase(declared_href=cast("str", object())), "declared_href"),
        (
            lambda: DocumentStructureSnapshot(
                references=cast("tuple[str, ...]", ["relative"])
            ),
            "references",
        ),
    ],
)
def test_preparation_values_reject_invalid_runtime_types(
    factory: Any,
    field: str,
) -> None:
    with pytest.raises(InvalidRenderInputError) as raised:
        factory()

    assert raised.value.field == field


def test_prepared_html_rejects_invalid_nested_snapshots() -> None:
    prepared = parse_html("<p>valid</p>")

    with pytest.raises(InvalidRenderInputError) as raised:
        replace(prepared, assets=cast("tuple[PreparedAsset, ...]", (object(),)))

    assert raised.value.operation == "prepared_html.create"
    assert raised.value.field == "assets"


@pytest.mark.parametrize("ratio", [0.0, -1.0, math.nan, math.inf, -math.inf])
def test_raster_options_reject_invalid_device_pixel_ratio(ratio: float) -> None:
    with pytest.raises(InvalidRenderInputError, match="finite and positive"):
        RasterOptions(device_pixel_ratio=ratio)


def test_raster_options_use_stable_validation_errors() -> None:
    with pytest.raises(InvalidRenderInputError, match="width"):
        RasterOptions(width=0)
    with pytest.raises(InvalidRenderInputError, match="height"):
        RasterOptions(height=-1)
    with pytest.raises(InvalidRenderInputError, match="format"):
        RasterOptions(format=cast("Literal['png', 'jpeg']", "gif"))
    with pytest.raises(InvalidRenderInputError, match="only supported for JPEG"):
        RasterOptions(quality=80)
    with pytest.raises(InvalidRenderInputError, match="between 0 and 100"):
        RasterOptions(format="jpeg", quality=101)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("width", True),
        ("width", "800"),
        ("height", False),
        ("height", "600"),
        ("device_pixel_ratio", True),
        ("device_pixel_ratio", "2"),
        ("quality", False),
        ("quality", "80"),
    ],
)
def test_raster_options_reject_invalid_runtime_types(
    field: str,
    value: object,
) -> None:
    arguments: dict[str, Any] = {field: value}
    if field == "quality":
        arguments["format"] = "jpeg"

    with pytest.raises(InvalidRenderInputError) as captured:
        RasterOptions(**arguments)

    assert captured.value.operation == "raster.configure"
    assert captured.value.field == field


async def test_prepare_text_uses_injected_template_and_reader(
    tmp_path: Path,
    preparer: DefaultHtmlPreparer,
) -> None:
    css = tmp_path / "text.css"
    css.write_text(".text { color: rebeccapurple; }", encoding="utf-8")
    prepared = await preparer.prepare_text(
        "<hello>",
        stylesheet=FileResourceRef(css),
    )
    assert "&lt;hello&gt;" in prepared.html
    assert prepared.stylesheets[0].base_url == css.resolve().as_uri()


async def test_prepare_markdown_reads_source_and_marks_math(
    tmp_path: Path,
    preparer: DefaultHtmlPreparer,
) -> None:
    source = tmp_path / "document.md"
    source.write_text(
        "# Title\n\n$$x^2$$\n\n<blockquote><p>Thinking</p></blockquote>",
        encoding="utf-8",
    )
    prepared = await preparer.prepare_markdown(FileResourceRef(source))
    assert "<h1>Title</h1>" in prepared.html
    assert "<blockquote><p>Thinking</p></blockquote>" in prepared.html
    assert "&lt;h1&gt;" not in prepared.html
    assert DocumentRequirement.JAVASCRIPT in prepared.requirements


async def test_cpu_bound_preparation_runs_outside_the_event_loop(
    preparer: DefaultHtmlPreparer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from entari_plugin_htmlrender.preparation import service  # noqa: PLC0415

    event_loop_thread = threading.get_ident()
    parser_threads: list[int] = []
    markdown_threads: list[int] = []
    original_parse_html = service.parse_html
    original_markdown = service.markdown.markdown

    def recording_parse_html(*args: Any, **kwargs: Any) -> PreparedHtml:
        parser_threads.append(threading.get_ident())
        return original_parse_html(*args, **kwargs)

    def recording_markdown(*args: Any, **kwargs: Any) -> str:
        markdown_threads.append(threading.get_ident())
        return original_markdown(*args, **kwargs)

    monkeypatch.setattr(service, "parse_html", recording_parse_html)
    monkeypatch.setattr(service.markdown, "markdown", recording_markdown)

    await preparer.prepare_html("<p>hello</p>")
    await preparer.prepare_markdown("# Title")

    assert parser_threads and markdown_threads
    assert all(
        thread != event_loop_thread for thread in (*parser_threads, *markdown_threads)
    )


async def test_prepare_markdown_translates_invalid_generated_urls(
    preparer: DefaultHtmlPreparer,
) -> None:
    with pytest.raises(InvalidRenderInputError, match="could not be resolved"):
        await preparer.prepare_markdown("![](http://[)")


async def test_prepare_markdown_accepts_empty_inline_content(
    preparer: DefaultHtmlPreparer,
) -> None:
    prepared = await preparer.prepare_markdown("")

    assert prepared.html


async def test_prepare_markdown_string_that_looks_like_path_is_inline(
    tmp_path: Path,
    preparer: DefaultHtmlPreparer,
) -> None:
    (tmp_path / "document.md").write_text("# File content", encoding="utf-8")

    prepared = await preparer.prepare_markdown("document.md")

    assert "document.md" in prepared.html
    assert "File content" not in prepared.html


def test_template_ref_requires_logical_name(
    tmp_path: Path,
) -> None:
    with pytest.raises(InvalidRenderInputError) as exc_info:
        TemplateRef(tmp_path, "")

    assert exc_info.value.operation == "create_template_ref"
    assert exc_info.value.field == "name"


def test_template_ref_freezes_relative_root_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    template = TemplateRef(Path("templates"), "card.html")

    monkeypatch.chdir(tmp_path.parent)

    assert template.root == tmp_path / "templates"


def test_template_ref_normalizes_parent_segments_without_resolving_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    normalized = TemplateRef(Path("a/../templates"), "card.html")
    direct = TemplateRef(Path("templates"), "card.html")

    assert normalized == direct
    assert hash(normalized) == hash(direct)


async def test_prepare_template_translates_template_engine_errors(
    tmp_path: Path,
    preparer: DefaultHtmlPreparer,
) -> None:
    with pytest.raises(ResourceNotFoundError, match="not found"):
        await preparer.prepare_template(TemplateRef(tmp_path, "missing.html"), {})


async def test_prepare_template_keeps_directory_base(
    tmp_path: Path,
    preparer: DefaultHtmlPreparer,
) -> None:
    (tmp_path / "card.html").write_text(
        "<strong>{{ name }}</strong>",
        encoding="utf-8",
    )
    prepared = await preparer.prepare_template(
        TemplateRef(tmp_path, "card.html"),
        {"name": "takumi"},
    )
    assert prepared.html == "<strong>takumi</strong>"
    assert (
        prepared.document_base.preparation_base_url == f"{tmp_path.resolve().as_uri()}/"  # noqa: ASYNC240
    )
