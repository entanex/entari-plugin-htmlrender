"""Managed Takumi adapter contracts and regression tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import anyio
import pytest

from entari_plugin_htmlrender.adapters.takumi import advanced as advanced_module
from entari_plugin_htmlrender.adapters.takumi.advanced import TakumiAPIAdapter
from entari_plugin_htmlrender.adapters.takumi.api import TakumiSessionAdapter
from entari_plugin_htmlrender.adapters.takumi.config import TakumiConfig
from entari_plugin_htmlrender.adapters.takumi.errors import (
    TakumiInputError,
    TakumiResourceError,
    TakumiRuntimeError,
    TakumiUnsupportedError,
)
from entari_plugin_htmlrender.adapters.takumi.runtime import TakumiRuntimeState
from entari_plugin_htmlrender.adapters.takumi.source import TakumiDocument
from entari_plugin_htmlrender.capabilities import (
    TakumiCompiledDocument,
    TakumiImageResource,
    TakumiKeyframesInput,
)
from entari_plugin_htmlrender.errors import (
    HtmlRenderError,
    InvalidRenderInputError,
    ProviderExecutionError,
    ResourceFetchError,
    RuntimeUnavailableError,
    UnsupportedDocumentFeatureError,
)
from entari_plugin_htmlrender.preparation import parse_html
from tests.adapters.takumi.helpers import resource_service

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from entari_plugin_htmlrender.adapters.takumi.types import NativeRenderer
    from entari_plugin_htmlrender.capabilities.takumi import (
        NativeCompiledNode,
        NativeCompiledStyleSheet,
    )
    from tests.adapters.conftest import RecordingOperationObserver


class _Renderer:
    pass


def _state(config: TakumiConfig | None = None) -> TakumiRuntimeState:
    return TakumiRuntimeState(
        renderer=cast("NativeRenderer", _Renderer()),
        limiter=anyio.Semaphore(1),
        config=config or TakumiConfig(),
        resources=resource_service(),
    )


async def test_compile_html_materializes_resources_and_binds_output(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    node = object()
    compiled_stylesheet = object()
    image = TakumiImageResource("memory:avatar", b"image")
    state = _state()
    materialize = mocker.patch.object(
        advanced_module,
        "materialize_takumi_document",
        new=mocker.AsyncMock(
            return_value=TakumiDocument(
                html="<p>materialized</p>",
                stylesheets=("p { color: red }",),
                images=(image,),
            )
        ),
    )
    compile_document = mocker.patch.object(
        TakumiRuntimeState,
        "compile_document",
        new=mocker.AsyncMock(return_value=(node, (compiled_stylesheet,))),
    )
    mocker.patch.object(advanced_module, "_expect_compiled_node", return_value=node)
    mocker.patch.object(
        advanced_module,
        "_expect_compiled_stylesheet",
        return_value=compiled_stylesheet,
    )

    document = await TakumiAPIAdapter(state, operation_observer).compile_html(
        '<img src="memory:avatar"><p>source</p>',
        stylesheets=("p { color: red }",),
        images=[image],
        base_url="memory:document.html",
    )

    assert document.node is node
    assert document.stylesheets == (compiled_stylesheet,)
    assert document.images == (image,)
    materialize_call = materialize.await_args
    assert materialize_call is not None
    prepared = materialize_call.args[0]
    assert prepared.document_base.preparation_base_url == "memory:document.html"
    assert materialize_call.kwargs["stylesheets"] == ("p { color: red }",)
    assert materialize_call.kwargs["images"] == [image]
    compile_document.assert_awaited_once_with(
        "<p>materialized</p>",
        ("p { color: red }",),
    )
    assert operation_observer.operations[-1] == (
        "takumi.api.compile_html",
        {"render.backend": "takumi"},
        "success",
    )


async def test_managed_compilers_forward_representative_arguments(
    mocker: MockerFixture,
) -> None:
    compiled_node = object()
    compiled_stylesheet = object()
    invoke = mocker.patch.object(
        TakumiRuntimeState,
        "invoke_renderer",
        new=mocker.AsyncMock(side_effect=(compiled_node, compiled_stylesheet)),
    )
    compile_stylesheet = mocker.patch.object(
        TakumiRuntimeState,
        "compile_stylesheet",
        new=mocker.AsyncMock(return_value=compiled_stylesheet),
    )
    mocker.patch.object(
        advanced_module,
        "_expect_compiled_stylesheet",
        return_value=compiled_stylesheet,
    )
    api = TakumiAPIAdapter(_state())
    node_input: dict[str, object] = {"type": "container"}
    keyframes: TakumiKeyframesInput = {
        "fade": {"from": {"opacity": 0}, "to": {"opacity": 1}}
    }

    assert await api.compile_node(node_input, validate=True) is compiled_node
    assert await api.compile_keyframes(keyframes) is compiled_stylesheet
    assert (
        await api.compile_stylesheet("div { color: red }", lossy=True)
        is compiled_stylesheet
    )

    node_call, keyframes_call = invoke.await_args_list
    assert node_call.args[0].__name__ == "compile_node"
    assert node_call.args[1:] == (node_input,)
    assert node_call.kwargs == {"validate": True}
    assert keyframes_call.args[0].__name__ == "compile_keyframes"
    assert keyframes_call.args[1:] == (keyframes,)
    compile_stylesheet.assert_awaited_once_with(
        "div { color: red }",
        lossy=True,
    )


async def test_node_rendering_converts_css_pixels_and_managed_options(
    mocker: MockerFixture,
) -> None:
    call_renderer = mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(return_value=b"png"),
    )
    api = TakumiAPIAdapter(_state())
    node: dict[str, object] = {"type": "container"}
    image = TakumiImageResource("memory:image", b"image")

    rendered = await api.render_node(
        node,
        stylesheets=["div { color: red }"],
        images=[image],
        validate=True,
        width=10,
        height=20,
        device_pixel_ratio=2,
        format="jpeg",
        quality=83,
        font_families=["Fixture Sans"],
        lang="en",
        time_ms=40,
    )

    assert rendered == b"png"
    call = call_renderer.await_args
    assert call is not None
    assert call.args == ("render_node", node)
    native = call.kwargs
    assert native["width"] == 20
    assert native["height"] == 40
    assert native["device_pixel_ratio"] == 2.0
    assert native["format"] == "jpeg"
    assert native["quality"] == 83
    assert native["time_ms"] == 40
    assert native["stylesheets"] == ("div { color: red }",)
    assert native["images"] == (image,)
    assert native["font_families"] == ("Fixture Sans",)
    assert native["lang"] == "en"
    assert native["validate"] is True


async def test_animation_operations_forward_managed_timing_contracts(
    mocker: MockerFixture,
) -> None:
    call_renderer = mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(side_effect=(b"animation", b"frame", b"encoded")),
    )
    api = TakumiAPIAdapter(_state())

    assert (
        await api.render_animation(
            (),
            width=10,
            height=20,
            device_pixel_ratio=2,
            format="gif",
            fps=12,
        )
        == b"animation"
    )
    assert (
        await api.render_sequence_at_time(
            (),
            75,
            width=10,
            height=20,
            format="jpeg",
            quality=77,
        )
        == b"frame"
    )
    assert await api.encode_frames((), format="webp", quality=80) == b"encoded"

    animation, sequence, encoded = call_renderer.await_args_list
    assert animation.args == ("render_animation", ())
    assert animation.kwargs["width"] == 20
    assert animation.kwargs["height"] == 40
    assert animation.kwargs["format"] == "gif"
    assert animation.kwargs["fps"] == 12
    assert sequence.args == ("render_sequence_at_time", (), 75)
    assert sequence.kwargs["format"] == "jpeg"
    assert "time_ms" not in sequence.kwargs
    assert encoded.args == ("encode_frames", ())
    assert encoded.kwargs["format"] == "webp"
    assert encoded.kwargs["quality"] == 80


async def test_compiled_operations_share_document_ownership_and_resources(
    mocker: MockerFixture,
) -> None:
    measured = object()
    node = cast("NativeCompiledNode", object())
    compiled_stylesheet = cast("NativeCompiledStyleSheet", object())
    call_renderer = mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(side_effect=(b"png", measured, "<svg/>")),
    )
    mocker.patch.object(
        advanced_module,
        "_expect_measured_node",
        return_value=measured,
    )
    api = TakumiAPIAdapter(_state())
    if api._lease_guard is None:
        raise AssertionError("adapter must own a lease guard")
    image = TakumiImageResource("memory:image", b"image")
    document = TakumiCompiledDocument(
        node=node,
        stylesheets=(compiled_stylesheet,),
        images=(image,),
        _lease_guard=api._lease_guard,
    )

    assert await api.render_compiled(document, width=12, height=8) == b"png"
    assert await api.measure_compiled(document, width=12, height=8) is measured
    assert await api.render_svg_compiled(document, width=12, height=8) == "<svg/>"

    assert [call.args[0] for call in call_renderer.await_args_list] == [
        "render_compiled",
        "measure_compiled",
        "render_svg_compiled",
    ]
    assert all(
        call.kwargs["stylesheets"] == document.stylesheets
        for call in call_renderer.await_args_list
    )
    assert all(
        call.kwargs["images"] == document.images
        for call in call_renderer.await_args_list
    )


async def test_compiled_document_is_bound_to_one_runtime_and_lease(
    mocker: MockerFixture,
) -> None:
    state = _state()
    owner = TakumiAPIAdapter(state)
    if owner._lease_guard is None:
        raise AssertionError("adapter must own a lease guard")
    document = TakumiCompiledDocument(
        node=cast("NativeCompiledNode", object()),
        stylesheets=(),
        _lease_guard=owner._lease_guard,
    )
    call_renderer = mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(return_value=b"png"),
    )

    with pytest.raises(RuntimeUnavailableError) as same_runtime_other_lease:
        await TakumiAPIAdapter(state).render_compiled(document)
    assert same_runtime_other_lease.value.state == "foreign_lease"

    with pytest.raises(RuntimeUnavailableError) as other_runtime:
        await TakumiAPIAdapter(_state()).render_compiled(document)
    assert other_runtime.value.state == "foreign_runtime"

    owner._lease_guard.invalidate()
    with pytest.raises(RuntimeUnavailableError) as expired:
        await owner.render_compiled(document)
    assert expired.value.state == "lease_expired"
    call_renderer.assert_not_awaited()


async def test_manually_constructed_compiled_document_is_rejected() -> None:
    document = TakumiCompiledDocument(
        node=cast("NativeCompiledNode", object()),
        stylesheets=(),
    )

    with pytest.raises(RuntimeUnavailableError) as raised:
        await TakumiAPIAdapter(_state()).render_compiled(document)

    assert raised.value.state == "unleased_document"


async def test_font_operations_forward_representative_native_contracts(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    register = mocker.patch.object(
        TakumiRuntimeState,
        "register_font",
        new=mocker.AsyncMock(return_value=("One",)),
    )
    register_many = mocker.patch.object(
        TakumiRuntimeState,
        "register_fonts",
        new=mocker.AsyncMock(return_value=("One", "Two")),
    )
    register_file = mocker.patch.object(
        TakumiRuntimeState,
        "register_font_file",
        new=mocker.AsyncMock(return_value=("File",)),
    )
    cache_font = mocker.patch.object(
        TakumiRuntimeState,
        "cache_font",
        new=mocker.AsyncMock(return_value=("Cached",)),
    )
    cached_fonts = mocker.patch.object(
        TakumiRuntimeState,
        "cached_fonts",
        new=mocker.AsyncMock(return_value=("Cached",)),
    )
    unregister = mocker.patch.object(
        TakumiRuntimeState,
        "unregister_font",
        new=mocker.AsyncMock(return_value=True),
    )
    clear = mocker.patch.object(
        TakumiRuntimeState,
        "clear_fonts",
        new=mocker.AsyncMock(return_value=None),
    )
    api = TakumiAPIAdapter(_state(), operation_observer)

    assert await api.register_font(b"one", source="memory:one") == ("One",)
    assert await api.register_fonts(
        [b"one", b"two"],
        sources=["memory:one", None],
    ) == ("One", "Two")
    assert await api.register_font_file(
        "font.ttf",
        name="File",
        unicode_range=[(0x20, 0x7E)],
    ) == ("File",)
    assert await api.cache_font(b"font", "memory:font") == ("Cached",)
    assert await api.cached_fonts("memory:font", pin=True) == ("Cached",)
    assert await api.unregister_font("Cached")
    await api.clear_fonts()

    register.assert_awaited_once_with(b"one", source="memory:one")
    register_many.assert_awaited_once_with(
        [b"one", b"two"],
        sources=["memory:one", None],
    )
    file_call = register_file.await_args
    assert file_call is not None
    assert file_call.kwargs["name"] == "File"
    assert file_call.kwargs["unicode_range"] == [(0x20, 0x7E)]
    assert (
        file_call.kwargs["cache_policy"] is advanced_module.FileCachePolicy.REVALIDATE
    )
    cache_font.assert_awaited_once_with(b"font", "memory:font")
    cached_fonts.assert_awaited_once_with("memory:font", pin=True)
    unregister.assert_awaited_once_with("Cached")
    clear.assert_awaited_once_with()
    assert [operation[0] for operation in operation_observer.operations] == [
        "takumi.api.register_font",
        "takumi.api.register_fonts",
        "takumi.api.register_font_file",
        "takumi.api.cache_font",
        "takumi.api.cached_fonts",
        "takumi.api.unregister_font",
        "takumi.api.clear_fonts",
    ]


@pytest.mark.parametrize("field", ["width", "device_pixel_ratio"])
async def test_invalid_dimensions_use_the_managed_input_error_boundary(
    mocker: MockerFixture,
    field: str,
) -> None:
    call_renderer = mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(),
    )
    api = TakumiAPIAdapter(_state())

    with pytest.raises(InvalidRenderInputError) as raised:
        if field == "width":
            await api.render_node({"type": "container"}, width=0)
        else:
            await api.render_node({"type": "container"}, device_pixel_ratio=0)

    assert raised.value.operation == "takumi.api.render_node"
    assert raised.value.field == field
    call_renderer.assert_not_awaited()


async def test_empty_html_uses_the_managed_input_error_boundary() -> None:
    api = TakumiAPIAdapter(_state())

    with pytest.raises(InvalidRenderInputError) as raised:
        await api.render_html("")

    assert raised.value.operation == "takumi.api.render_html"
    assert raised.value.field == "prepared.html"


@pytest.mark.parametrize(
    ("operation", "expected_operation"),
    [
        ("api", "takumi.api.render_svg_node"),
        ("session", "takumi.render_svg_html"),
    ],
)
async def test_invalid_svg_dimension_uses_the_managed_input_error_boundary(
    operation: str,
    expected_operation: str,
) -> None:
    state = _state()

    with pytest.raises(InvalidRenderInputError) as raised:
        if operation == "api":
            await TakumiAPIAdapter(state).render_svg_node(
                {"type": "container"},
                width=0,
            )
        else:
            await TakumiSessionAdapter(state).render_svg_html(
                "<div>svg</div>",
                width=0,
            )

    assert raised.value.operation == expected_operation
    assert raised.value.field == "width"


async def test_font_source_count_mismatch_uses_the_managed_input_error_boundary() -> (
    None
):
    api = TakumiAPIAdapter(_state())

    with pytest.raises(InvalidRenderInputError) as raised:
        await api.register_fonts([b"font"], sources=())

    assert raised.value.operation == "takumi.api.register_fonts"
    assert raised.value.field == "fonts.sources"


async def test_expired_lease_rejects_new_managed_operations() -> None:
    api = TakumiAPIAdapter(_state())
    if api._lease_guard is None:
        raise AssertionError("adapter must own a lease guard")
    api._lease_guard.invalidate()

    with pytest.raises(RuntimeUnavailableError) as raised:
        await api.cache_font(b"font", "memory:font")

    assert raised.value.state == "lease_expired"
    assert raised.value.operation == "takumi.api.cache_font"


def test_read_only_state_and_prepared_input_share_lease_validation() -> None:
    api = TakumiAPIAdapter(_state())
    prepared = parse_html("<p>prepared</p>")

    assert api.registered_font_families == ()
    assert api.compiled_cache_stats.entries == 0
    assert api._prepared(prepared, "ignored") is prepared

    object.__setattr__(api, "_lease_guard", None)
    with pytest.raises(TakumiRuntimeError, match="no active lease guard"):
        api._ensure_open("takumi.api.test")
    with pytest.raises(TakumiRuntimeError, match="no active lease guard"):
        api._ensure_document(
            cast("TakumiCompiledDocument", object()),
            "takumi.api.test",
        )


@pytest.mark.parametrize(
    ("validator_name", "message"),
    [
        ("_expect_bytes", "expected bytes"),
        ("_expect_svg", "expected str"),
        ("_expect_compiled_node", "expected CompiledNode"),
        ("_expect_compiled_stylesheet", "expected CompiledStyleSheet"),
        ("_expect_measured_node", "expected MeasuredNode"),
    ],
)
def test_native_result_validators_reject_wrong_types(
    validator_name: str,
    message: str,
) -> None:
    pytest.importorskip("takumi_py")
    validator = getattr(advanced_module, validator_name)

    with pytest.raises(TakumiRuntimeError, match=message):
        validator(object())


def test_native_result_validators_accept_matching_values() -> None:
    takumi_py = pytest.importorskip("takumi_py")
    renderer = takumi_py.Renderer()
    compiled_node = renderer.compile_node({"type": "container"})
    compiled_stylesheet = renderer.compile_stylesheet("div { color: red }")
    measured = takumi_py.MeasuredNode(
        width=1.0,
        height=1.0,
        transform=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        children=(),
        runs=(),
    )

    assert advanced_module._expect_compiled_node(compiled_node) is compiled_node
    assert (
        advanced_module._expect_compiled_stylesheet(compiled_stylesheet)
        is compiled_stylesheet
    )
    assert advanced_module._expect_measured_node(measured) is measured


@pytest.mark.parametrize(
    ("error", "expected_public_error"),
    [
        pytest.param(
            TakumiInputError("node", "invalid"),
            InvalidRenderInputError,
            id="input",
        ),
        pytest.param(
            TakumiResourceError("missing", reference="memory:missing"),
            ResourceFetchError,
            id="resource",
        ),
        pytest.param(
            TakumiUnsupportedError("javascript", "unsupported"),
            UnsupportedDocumentFeatureError,
            id="unsupported",
        ),
        pytest.param(
            TakumiRuntimeError("runtime failed"),
            ProviderExecutionError,
            id="runtime",
        ),
        pytest.param(
            TypeError("invalid duck input"),
            InvalidRenderInputError,
            id="raw-type-error",
        ),
        pytest.param(
            ValueError("adapter failed"),
            ProviderExecutionError,
            id="unknown",
        ),
    ],
)
async def test_advanced_api_uses_the_stable_managed_error_boundary(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
    error: Exception,
    expected_public_error: type[HtmlRenderError],
) -> None:
    mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(side_effect=error),
    )
    api = TakumiAPIAdapter(_state(), operation_observer)

    with pytest.raises(expected_public_error) as raised:
        await api.render_node({"type": "container"})

    assert raised.value.__cause__ is error
    assert isinstance(
        raised.value,
        (
            InvalidRenderInputError,
            ProviderExecutionError,
            ResourceFetchError,
            UnsupportedDocumentFeatureError,
        ),
    )
    assert raised.value.operation == "takumi.api.render_node"
    assert operation_observer.operations[-1] == (
        "takumi.api.render_node",
        {"render.backend": "takumi"},
        "error",
    )


async def test_closed_runtime_rejects_advanced_calls_through_public_errors(
    operation_observer: RecordingOperationObserver,
) -> None:
    state = _state()
    await state.aclose()
    api = TakumiAPIAdapter(state, operation_observer)

    with pytest.raises(ProviderExecutionError, match="closed") as raised:
        await api.render_node({"type": "container"})

    assert isinstance(raised.value.__cause__, TakumiRuntimeError)
    assert operation_observer.operations[-1][-1] == "error"
