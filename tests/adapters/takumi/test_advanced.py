"""Advanced Takumi API mapping, observation, and error-boundary tests."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, cast, get_type_hints

import anyio
import pytest

from entari_plugin_htmlrender.adapters.takumi import advanced as advanced_module
from entari_plugin_htmlrender.adapters.takumi.advanced import TakumiAPIAdapter
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
    from tests.adapters.conftest import RecordingOperationObserver


class _Renderer:
    pass


class _WorkerRenderer:
    def __init__(self) -> None:
        self.thread = 0

    def render_node(self, node: object, **kwargs: object) -> bytes:
        del node, kwargs
        self.thread = threading.get_ident()
        return b"png"


def _state(config: TakumiConfig | None = None) -> TakumiRuntimeState:
    return TakumiRuntimeState(
        renderer=cast("NativeRenderer", _Renderer()),
        limiter=anyio.Semaphore(1),
        config=config or TakumiConfig(),
        resources=resource_service(),
    )


async def test_compile_html_reuses_document_cache_and_preserves_images(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    node = object()
    stylesheet = object()
    image = TakumiImageResource("memory:avatar", b"image")
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
        new=mocker.AsyncMock(return_value=(node, (stylesheet,))),
    )
    mocker.patch.object(advanced_module, "_expect_compiled_node", return_value=node)
    mocker.patch.object(
        advanced_module,
        "_expect_compiled_stylesheet",
        return_value=stylesheet,
    )

    document = await TakumiAPIAdapter(
        _state(),
        operation_observer,
    ).compile_html(
        '<img src="memory:avatar"><p>source</p>',
        stylesheets=("p { color: red }",),
        images=[image],
        base_url="memory:document.html",
    )

    assert document.node is node
    assert document.stylesheets == (stylesheet,)
    assert document.images == (image,)
    prepared_call = materialize.await_args
    assert prepared_call is not None
    assert prepared_call.kwargs["stylesheets"] == ("p { color: red }",)
    assert prepared_call.kwargs["images"] == [image]
    compile_document.assert_awaited_once_with(
        "<p>materialized</p>",
        ("p { color: red }",),
    )
    assert operation_observer.operations[-1] == (
        "takumi.api.compile_html",
        {"render.backend": "takumi"},
        "success",
    )


async def test_native_compilers_keep_their_exact_argument_mapping(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
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
    api = TakumiAPIAdapter(_state(), operation_observer)
    node_input: dict[str, object] = {"type": "container"}
    keyframes: TakumiKeyframesInput = {
        "fade": {
            "from": {"opacity": 0},
            "to": {"opacity": 1},
        }
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
    assert keyframes_call.kwargs == {}
    compile_stylesheet.assert_awaited_once_with(
        "div { color: red }",
        lossy=True,
    )


async def test_node_rendering_maps_css_dimensions_and_native_options(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    call_renderer = mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(return_value=b"png"),
    )
    api = TakumiAPIAdapter(_state(), operation_observer)
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
    assert call.kwargs == {
        "stylesheets": ("div { color: red }",),
        "images": (image,),
        "validate": True,
        "width": 20,
        "height": 40,
        "format": "jpeg",
        "font_size": 16.0,
        "device_pixel_ratio": 2.0,
        "draw_debug_border": False,
        "dithering": "none",
        "time_ms": 40,
        "quality": 83,
        "font_families": ("Fixture Sans",),
        "lang": "en",
    }


async def test_native_advanced_work_runs_outside_the_event_loop_thread() -> None:
    renderer = _WorkerRenderer()
    state = TakumiRuntimeState(
        renderer=cast("NativeRenderer", renderer),
        limiter=anyio.Semaphore(1),
        config=TakumiConfig(),
        resources=resource_service(),
    )
    event_loop_thread = threading.get_ident()

    assert await TakumiAPIAdapter(state).render_node({"type": "container"}) == b"png"
    assert renderer.thread != event_loop_thread


async def test_compiled_measurement_and_svg_paths_share_one_document(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    takumi_py = pytest.importorskip("takumi_py")
    measured = takumi_py.MeasuredNode(
        width=12.0,
        height=8.0,
        transform=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        children=(),
        runs=(),
    )
    call_renderer = mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(side_effect=(b"png", measured, "<svg/>")),
    )
    compiled_node = takumi_py.Renderer().compile_node({"type": "container"})
    mocker.patch.object(
        TakumiRuntimeState,
        "compile_document",
        new=mocker.AsyncMock(return_value=(compiled_node, ())),
    )
    mocker.patch.object(
        advanced_module,
        "_expect_compiled_node",
        return_value=compiled_node,
    )
    api = TakumiAPIAdapter(_state(), operation_observer)
    document = await api.compile_html("<div>compiled</div>")

    assert await api.render_compiled(document, width=12, height=8) == b"png"
    assert await api.measure_compiled(document, width=12, height=8) is measured
    assert await api.render_svg_compiled(document, width=12, height=8) == "<svg/>"

    assert [call.args[0] for call in call_renderer.await_args_list] == [
        "render_compiled",
        "measure_compiled",
        "render_svg_compiled",
    ]
    assert all(
        call.kwargs["stylesheets"] == () for call in call_renderer.await_args_list
    )
    assert all(
        call.kwargs["images"] == document.images
        for call in call_renderer.await_args_list
    )


async def test_compiled_document_is_bound_to_one_runtime_and_lease(
    mocker: MockerFixture,
) -> None:
    takumi_py = pytest.importorskip("takumi_py")
    compiled_node = takumi_py.Renderer().compile_node({"type": "container"})
    mocker.patch.object(
        TakumiRuntimeState,
        "compile_document",
        new=mocker.AsyncMock(return_value=(compiled_node, ())),
    )
    mocker.patch.object(
        advanced_module,
        "_expect_compiled_node",
        return_value=compiled_node,
    )
    state = _state()
    owner = TakumiAPIAdapter(state)
    document = await owner.compile_html("<div>owned</div>")

    with pytest.raises(RuntimeUnavailableError) as same_runtime_other_lease:
        await TakumiAPIAdapter(state).render_compiled(document)
    assert same_runtime_other_lease.value.state == "foreign_lease"

    with pytest.raises(RuntimeUnavailableError) as other_runtime:
        await TakumiAPIAdapter(_state()).render_compiled(document)
    assert other_runtime.value.state == "foreign_runtime"

    if owner._lease_guard is None:
        raise AssertionError("adapter must own a lease guard")
    owner._lease_guard.invalidate()
    with pytest.raises(RuntimeUnavailableError) as expired:
        await owner.render_compiled(document)
    assert expired.value.state == "lease_expired"


async def test_manually_constructed_compiled_document_is_rejected() -> None:
    takumi_py = pytest.importorskip("takumi_py")
    document = TakumiCompiledDocument(
        node=takumi_py.Renderer().compile_node({"type": "container"}),
        stylesheets=(),
    )

    with pytest.raises(RuntimeUnavailableError) as raised:
        await TakumiAPIAdapter(_state()).render_compiled(document)

    assert raised.value.state == "unleased_document"


async def test_animation_sequence_and_frame_encoding_map_container_options(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    takumi_py = pytest.importorskip("takumi_py")
    call_renderer = mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(side_effect=(b"animation", b"frame", b"encoded")),
    )
    api = TakumiAPIAdapter(_state(), operation_observer)
    scenes = (
        takumi_py.AnimationScene(node={"type": "container"}, duration_ms=10),
        takumi_py.AnimationScene(node={"type": "container"}, duration_ms=20),
    )
    frames = (
        takumi_py.RawAnimationFrame(
            data=b"\x00" * 16,
            width=2,
            height=2,
            duration_ms=10,
        ),
    )

    assert (
        await api.render_animation(
            scenes,
            stylesheets=["div { color: red }"],
            validate=True,
            width=10,
            height=20,
            device_pixel_ratio=2,
            format="gif",
            fps=12,
            loop_count=3,
        )
        == b"animation"
    )
    assert (
        await api.render_sequence_at_time(
            scenes,
            75,
            width=10,
            height=20,
            format="jpeg",
            quality=77,
        )
        == b"frame"
    )
    assert (
        await api.encode_frames(
            frames,
            format="webp",
            quality=80,
            loop_count=2,
            webp_speed=4,
        )
        == b"encoded"
    )

    animation_call, sequence_call, encode_call = call_renderer.await_args_list
    assert animation_call.args == ("render_animation", scenes)
    assert animation_call.kwargs == {
        "stylesheets": ("div { color: red }",),
        "validate": True,
        "width": 20,
        "height": 40,
        "font_size": 16.0,
        "device_pixel_ratio": 2.0,
        "draw_debug_border": False,
        "dithering": "none",
        "fps": 12,
        "format": "gif",
        "webp_blend": True,
        "webp_dispose": False,
        "loop_count": 3,
    }
    assert sequence_call.args == ("render_sequence_at_time", scenes, 75)
    assert sequence_call.kwargs["width"] == 10
    assert sequence_call.kwargs["height"] == 20
    assert sequence_call.kwargs["format"] == "jpeg"
    assert sequence_call.kwargs["quality"] == 77
    assert "time_ms" not in sequence_call.kwargs
    assert encode_call.args == ("encode_frames", frames)
    assert encode_call.kwargs == {
        "format": "webp",
        "webp_blend": True,
        "webp_dispose": False,
        "quality": 80,
        "loop_count": 2,
        "webp_speed": 4,
    }


async def test_font_registration_reuses_the_runtime_admission_path(
    mocker: MockerFixture,
    operation_observer: RecordingOperationObserver,
) -> None:
    state = _state()
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
    api = TakumiAPIAdapter(state, operation_observer)

    assert await api.register_font(b"one", source="memory:one") == ("One",)
    assert await api.register_fonts(
        [b"one", b"two"],
        sources=["memory:one", None],
    ) == ("One", "Two")
    assert await api.register_font_file(
        "font.ttf",
        name="File",
        weight=600,
        style="normal",
        subset_of="Parent",
        generic_family="sans-serif",
    ) == ("File",)

    register.assert_awaited_once_with(b"one", source="memory:one")
    register_many.assert_awaited_once_with(
        [b"one", b"two"],
        sources=["memory:one", None],
    )
    register_file.assert_awaited_once_with(
        "font.ttf",
        name="File",
        weight=600,
        style="normal",
        subset_of="Parent",
        generic_family="sans-serif",
        cache_policy=advanced_module.FileCachePolicy.REVALIDATE,
    )


def test_properties_and_prepared_input_share_lease_validation() -> None:
    api = TakumiAPIAdapter(_state())
    prepared = parse_html("<p>prepared</p>")

    assert api.registered_font_families == ()
    assert api.compiled_cache_stats.entries == 0
    assert api._prepared(prepared, "ignored") is prepared


def test_native_result_validators_reject_wrong_types() -> None:
    pytest.importorskip("takumi_py")

    with pytest.raises(TakumiRuntimeError, match="expected bytes"):
        advanced_module._expect_bytes("<svg/>")
    with pytest.raises(TakumiRuntimeError, match="expected str"):
        advanced_module._expect_svg(b"png")
    with pytest.raises(TakumiRuntimeError, match="expected CompiledNode"):
        advanced_module._expect_compiled_node(object())
    with pytest.raises(TakumiRuntimeError, match="expected CompiledStyleSheet"):
        advanced_module._expect_compiled_stylesheet(object())
    with pytest.raises(TakumiRuntimeError, match="expected MeasuredNode"):
        advanced_module._expect_measured_node(object())


def test_missing_lease_guard_cannot_be_bypassed() -> None:
    state = _state()
    api = TakumiAPIAdapter(state)
    object.__setattr__(api, "_lease_guard", None)

    with pytest.raises(TakumiRuntimeError, match="no active lease guard"):
        api._ensure_open("takumi.api.test")
    with pytest.raises(TakumiRuntimeError, match="no active lease guard"):
        api._ensure_document(
            cast("TakumiCompiledDocument", object()),
            "takumi.api.test",
        )


@pytest.mark.parametrize(
    ("error", "expected_type"),
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
    expected_type: type[Exception],
) -> None:
    mocker.patch.object(
        TakumiRuntimeState,
        "call_renderer",
        new=mocker.AsyncMock(side_effect=error),
    )
    api = TakumiAPIAdapter(_state(), operation_observer)

    with pytest.raises(expected_type) as raised:
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


def test_advanced_annotations_are_runtime_resolvable() -> None:
    for name, value in vars(TakumiAPIAdapter).items():
        if callable(value) and not name.startswith("_"):
            assert get_type_hints(value)
    assert get_type_hints(TakumiAPIAdapter.compile_node)
    assert get_type_hints(TakumiAPIAdapter.compile_keyframes)
