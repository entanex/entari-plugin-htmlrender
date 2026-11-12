from __future__ import annotations

from functools import partial
import importlib
import os
from pathlib import Path
import py_compile
import sys
import threading
from types import ModuleType
from typing import TYPE_CHECKING, ParamSpec, TypedDict, TypeVar

import anyio
from anyio.to_thread import run_sync as run_in_thread
import pytest

from entari_plugin_htmlrender.graphics import drawing_loader
from entari_plugin_htmlrender.graphics.drawing_loader import (
    DrawingLoadError,
    DrawingNotFoundError,
    DrawingRegistry,
    DrawingSpec,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Protocol

    class _Card(Protocol):
        value: str


T = TypeVar("T")
P = ParamSpec("P")


class _SpecInputs(TypedDict, total=False):
    path: Path
    module: str


class _InlineWorker:
    def __init__(self) -> None:
        self.calls = 0

    async def run_sync(
        self,
        function: Callable[P, T],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        self.calls += 1
        return function(*args, **kwargs)


async def _leased(
    registry: DrawingRegistry,
    name: str,
    canvas: object,
    request: dict[str, object],
) -> None:
    async with registry.lease(name) as draw:
        draw(canvas, request)


def _owned_module_names() -> frozenset[str]:
    return frozenset(
        name for name in sys.modules if name.startswith("_entari_htmlrender_drawings")
    )


def _owned_finders() -> tuple[object, ...]:
    return tuple(
        finder for finder in sys.meta_path if type(finder).__name__ == "_DrawingFinder"
    )


def test_spec_and_name_contract(tmp_path: Path) -> None:
    spec = DrawingSpec("pillow", path=tmp_path / "draw.py")
    registry = DrawingRegistry({"card": spec}, worker=_InlineWorker())

    assert registry.names == frozenset({"card"})
    assert registry.spec("card") is spec
    with pytest.raises(DrawingNotFoundError):
        registry.spec("missing")


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"path": Path("one.py"), "module": "two"},
        {"module": ".relative"},
    ],
)
def test_spec_rejects_invalid_sources(kwargs: _SpecInputs) -> None:
    with pytest.raises((TypeError, ValueError)):
        DrawingSpec("skia", **kwargs)


async def test_file_definition_loads_lazily_and_runs_on_worker(
    tmp_path: Path,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(
        "def draw(canvas, request, *, ignored=None):\n"
        "    canvas.append((request['value'], ignored))\n",
        encoding="utf-8",
    )
    worker = _InlineWorker()
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source)},
        worker=worker,
    )
    canvas: list[tuple[object, object]] = []

    assert not worker.calls
    await _leased(registry, "card", canvas, {"value": 42})

    assert canvas == [(42, None)]
    assert worker.calls == 3
    await registry.aclose()


async def test_package_module_preserves_relative_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "drawing_package"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helpers.py").write_text(
        "VALUE = 'module'\n",
        encoding="utf-8",
    )
    (package / "draw.py").write_text(
        "from .helpers import VALUE\n"
        "def draw(canvas, request):\n"
        "    canvas.append(VALUE)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    before_path = tuple(sys.path)
    before_modules = _owned_module_names()
    registry = DrawingRegistry(
        {"card": DrawingSpec("skia", module="drawing_package.draw")},
        worker=_InlineWorker(),
    )
    canvas: list[object] = []

    await _leased(registry, "card", canvas, {})

    assert canvas == ["module"]
    assert tuple(sys.path) == before_path
    await registry.aclose()
    assert _owned_module_names() == before_modules


async def test_dataclass_and_relative_dependency_reload(
    tmp_path: Path,
) -> None:
    (tmp_path / "helpers").mkdir()
    (tmp_path / "helpers" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "helpers" / "tone.py").write_text(
        "TONE = 'red'\n",
        encoding="utf-8",
    )
    source = tmp_path / "draw.py"
    source.write_text(
        "from dataclasses import dataclass\n"
        "from .helpers.tone import TONE\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Card:\n"
        "    value: str = TONE\n"
        "def draw(canvas, request):\n"
        "    canvas.append(Card())\n",
        encoding="utf-8",
    )
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source, reload=True)},
        worker=_InlineWorker(),
    )

    async with registry.lease("card") as first_draw:
        first_canvas: list[_Card] = []
        first_draw(first_canvas, {})
    (tmp_path / "helpers" / "tone.py").write_text(
        "TONE = 'blue'\n",
        encoding="utf-8",
    )
    async with registry.lease("card") as second_draw:
        second_canvas: list[_Card] = []
        second_draw(second_canvas, {})

    assert second_draw is not first_draw
    assert first_canvas[0].value == "red"
    assert second_canvas[0].value == "blue"
    await registry.aclose()


async def test_same_size_same_mtime_content_change_is_detected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('a')\n",
        encoding="utf-8",
    )
    size = source.stat().st_size
    fixed_ns = 1_700_000_000_000_000_000
    os.utime(source, ns=(fixed_ns, fixed_ns))
    py_compile.compile(str(source), doraise=True)
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source, reload=True)},
        worker=_InlineWorker(),
    )
    first: list[str] = []
    await _leased(registry, "card", first, {})

    source.write_text(
        "def draw(canvas, request):\n    canvas.append('b')\n",
        encoding="utf-8",
    )
    assert source.stat().st_size == size
    os.utime(source, ns=(fixed_ns, fixed_ns))
    second: list[str] = []
    await _leased(registry, "card", second, {})

    assert first == ["a"]
    assert second == ["b"]
    await registry.aclose()


async def test_bad_syntax_keeps_previous_generation_and_logs_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('old')\n",
        encoding="utf-8",
    )
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source, reload=True)},
        worker=_InlineWorker(),
    )
    logged: list[object] = []
    monkeypatch.setattr(
        "entari_plugin_htmlrender.graphics.drawing_loader.logger.error",
        lambda *args: logged.append(args),
    )
    old: list[str] = []
    await _leased(registry, "card", old, {})
    source.write_text("def draw(\n", encoding="utf-8")

    retained: list[str] = []
    await _leased(registry, "card", retained, {})
    retained_again: list[str] = []
    await _leased(registry, "card", retained_again, {})

    assert old == ["old"]
    assert retained == ["old"]
    assert retained_again == ["old"]
    assert len(logged) == 1
    with pytest.raises(DrawingLoadError):
        await registry.reload("card")
    await registry.aclose()


@pytest.mark.parametrize(
    "source_text",
    [
        "async def draw(canvas, request):\n    pass\n",
        "def draw(canvas):\n    pass\n",
        "def draw(canvas, request, extra):\n    pass\n",
    ],
)
async def test_async_and_invalid_signatures_fail_without_residue(
    tmp_path: Path,
    source_text: str,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(source_text, encoding="utf-8")
    before = _owned_module_names()
    registry = DrawingRegistry(
        {"card": DrawingSpec("skia", path=source)},
        worker=_InlineWorker(),
    )

    with pytest.raises(DrawingLoadError):
        async with registry.lease("card"):
            pass

    assert _owned_module_names() == before
    await registry.aclose()


async def test_first_auto_load_error_is_not_swallowed(tmp_path: Path) -> None:
    source = tmp_path / "draw.py"
    source.write_text("def draw(canvas):\n    pass\n", encoding="utf-8")
    registry = DrawingRegistry(
        {"card": DrawingSpec("skia", path=source, reload=True)},
        worker=_InlineWorker(),
    )

    with pytest.raises(DrawingLoadError, match="two bindable positional"):
        async with registry.lease("card"):
            pass

    await registry.aclose()


async def test_explicit_reload_retries_the_same_failed_fingerprint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text("def draw(canvas):\n    pass\n", encoding="utf-8")
    registry = DrawingRegistry(
        {"card": DrawingSpec("skia", path=source)},
        worker=_InlineWorker(),
    )

    with pytest.raises(DrawingLoadError):
        await registry.reload("card")
    with pytest.raises(DrawingLoadError):
        await registry.reload("card")

    source.write_text(
        "def draw(canvas, request):\n    canvas.append(request['ok'])\n",
        encoding="utf-8",
    )
    await registry.reload("card")
    canvas: list[object] = []
    await _leased(registry, "card", canvas, {"ok": True})
    assert canvas == [True]
    await registry.aclose()


async def test_reload_disabled_ignores_changes_until_explicit_reload(
    tmp_path: Path,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('first')\n",
        encoding="utf-8",
    )
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source)},
        worker=_InlineWorker(),
    )
    initial: list[str] = []
    await _leased(registry, "card", initial, {})
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('second')\n",
        encoding="utf-8",
    )
    retained: list[str] = []

    await _leased(registry, "card", retained, {})
    await registry.reload("card")
    changed: list[str] = []
    await _leased(registry, "card", changed, {})

    assert initial == ["first"]
    assert retained == ["first"]
    assert changed == ["second"]
    await registry.aclose()


async def test_concurrent_leases_pin_old_generation_until_release(
    tmp_path: Path,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('old')\n",
        encoding="utf-8",
    )
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source, reload=True)},
        worker=_InlineWorker(),
    )
    entered = anyio.Event()
    release = anyio.Event()
    before_finders = _owned_finders()
    old_namespace: list[str] = []
    second: list[str] = []

    async def first() -> None:
        async with registry.lease("card") as draw:
            canvas: list[str] = []
            draw(canvas, {})
            old_namespace.append(
                next(
                    name
                    for name in _owned_module_names()
                    if f".{Path(source.stem).stem}" in name or name.endswith(".draw")
                )
            )
            entered.set()
            await release.wait()
            draw(canvas, {})
            assert canvas == ["old", "old"]

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(first)
        await entered.wait()
        source.write_text(
            "def draw(canvas, request):\n    canvas.append('new')\n",
            encoding="utf-8",
        )
        await registry.reload("card")

        async def second_render() -> None:
            await _leased(registry, "card", second, {})

        task_group.start_soon(second_render)
        await anyio.wait_all_tasks_blocked()
        assert len(_owned_finders()) == len(before_finders) + 2
        release.set()

    assert second == ["new"]
    assert old_namespace[0] not in sys.modules
    assert len(_owned_finders()) == len(before_finders) + 1
    await registry.aclose()
    assert len(_owned_finders()) == len(before_finders)


async def test_aclose_closes_generations_and_finders(
    tmp_path: Path,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(
        "import json\n"
        "def draw(canvas, request):\n    canvas.append(json.dumps(request))\n",
        encoding="utf-8",
    )
    before_modules = _owned_module_names()
    before_finders = _owned_finders()
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source)},
        worker=_InlineWorker(),
    )
    await _leased(registry, "card", [], {})
    assert _owned_module_names() > before_modules
    assert len(_owned_finders()) == len(before_finders) + 1

    await registry.aclose()

    assert _owned_module_names() == before_modules
    assert len(_owned_finders()) == len(before_finders)


async def test_relative_import_inside_draw_is_tracked(tmp_path: Path) -> None:
    source = tmp_path / "draw.py"
    helper = tmp_path / "helper.py"
    source.write_text(
        "def draw(canvas, request):\n"
        "    from .helper import VALUE\n"
        "    canvas.append(VALUE)\n",
        encoding="utf-8",
    )
    helper.write_text("VALUE = 'old'\n", encoding="utf-8")
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source, reload=True)},
        worker=_InlineWorker(),
    )
    first: list[str] = []
    await _leased(registry, "card", first, {})
    helper.write_text("VALUE = 'new'\n", encoding="utf-8")
    second: list[str] = []
    await _leased(registry, "card", second, {})
    assert first == ["old"]
    assert second == ["new"]
    await registry.aclose()


async def test_failed_new_helper_is_cached_then_recovers(tmp_path: Path) -> None:
    source = tmp_path / "draw.py"
    marker = tmp_path / "attempts"
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('old')\n",
        encoding="utf-8",
    )
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source, reload=True)},
        worker=_InlineWorker(),
    )
    await _leased(registry, "card", [], {})
    source.write_text(
        "from pathlib import Path\n"
        f"marker = Path({str(marker)!r})\n"
        "marker.write_text(marker.read_text() + 'x' if marker.exists() else 'x')\n"
        "from .new_helper import VALUE\n"
        "def draw(canvas, request):\n    canvas.append(VALUE)\n",
        encoding="utf-8",
    )
    retained: list[str] = []
    await _leased(registry, "card", retained, {})
    await _leased(registry, "card", retained, {})
    assert retained == ["old", "old"]
    assert marker.read_text() == "x"
    (tmp_path / "new_helper.py").write_text("VALUE = 'new'\n", encoding="utf-8")
    recovered: list[str] = []
    await _leased(registry, "card", recovered, {})
    assert recovered == ["new"]
    assert marker.read_text() == "xx"
    await registry.aclose()


async def test_import_time_rewrite_keeps_compiled_byte_fingerprint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('old')\n",
        encoding="utf-8",
    )
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source, reload=True)},
        worker=_InlineWorker(),
    )
    await _leased(registry, "card", [], {})
    before = _owned_module_names()
    replacement = "def draw(canvas, request):\n    canvas.append('new')\n"
    source.write_text(
        "from pathlib import Path\n"
        f"Path(__file__).write_text({replacement!r})\n"
        "def draw(canvas, request):\n    canvas.append('unstable')\n",
        encoding="utf-8",
    )
    retained: list[str] = []
    await _leased(registry, "card", retained, {})
    assert retained == ["old"]
    assert _owned_module_names() == before
    recovered: list[str] = []
    await _leased(registry, "card", recovered, {})
    assert recovered == ["new"]
    await registry.aclose()


async def test_module_removal_retains_last_good_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "removed_drawing.py"
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('old')\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", module="removed_drawing", reload=True)},
        worker=_InlineWorker(),
    )
    await _leased(registry, "card", [], {})
    source.unlink()
    retained: list[str] = []
    await _leased(registry, "card", retained, {})
    await _leased(registry, "card", retained, {})
    assert retained == ["old", "old"]
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('new')\n",
        encoding="utf-8",
    )
    recovered: list[str] = []
    await _leased(registry, "card", recovered, {})
    assert recovered == ["new"]
    await registry.aclose()


async def test_package_precedence_and_parent_initialization_are_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "initialized_drawing"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from .helper import VALUE\n", encoding="utf-8"
    )
    (package / "helper.py").write_text("VALUE = 'parent'\n", encoding="utf-8")
    (package / "entry.py").write_text(
        "raise RuntimeError('wrong file')\n", encoding="utf-8"
    )
    entry = package / "entry"
    entry.mkdir()
    (entry / "__init__.py").write_text(
        "from .. import VALUE\ndef draw(canvas, request):\n    canvas.append(VALUE)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    canonical = importlib.import_module("initialized_drawing")
    canonical_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "initialized_drawing" or name.startswith("initialized_drawing.")
    }
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", module="initialized_drawing.entry")},
        worker=_InlineWorker(),
    )
    try:
        canvas: list[str] = []
        await _leased(registry, "card", canvas, {})
        assert canvas == ["parent"]
        assert sys.modules["initialized_drawing"] is canonical
        assert not hasattr(canonical, "entry")
        assert {
            name: module
            for name, module in sys.modules.items()
            if name == "initialized_drawing" or name.startswith("initialized_drawing.")
        } == canonical_modules
    finally:
        await registry.aclose()
        for name in canonical_modules:
            sys.modules.pop(name, None)


async def test_explicit_file_and_dotted_filename_load(tmp_path: Path) -> None:
    source = tmp_path / "card.v2.py"
    source.write_text(
        "def draw(canvas, request):\n    canvas.append('file')\n",
        encoding="utf-8",
    )
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source)}, worker=_InlineWorker()
    )
    canvas: list[str] = []
    await _leased(registry, "card", canvas, {})
    assert canvas == ["file"]
    await registry.aclose()


async def test_failed_claim_preserves_unowned_namespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "draw.py"
    source.write_text("def draw(canvas, request):\n    pass\n", encoding="utf-8")
    namespace = "_entari_htmlrender_drawings_occupied_test"
    package = ModuleType(namespace)
    child = ModuleType(f"{namespace}.child")
    monkeypatch.setitem(sys.modules, namespace, package)
    monkeypatch.setitem(sys.modules, f"{namespace}.child", child)
    monkeypatch.setattr(drawing_loader, "_generation_namespace", lambda: namespace)
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source)}, worker=_InlineWorker()
    )
    with pytest.raises(DrawingLoadError, match="already occupied"):
        await registry.reload("card")
    await registry.aclose()
    assert sys.modules[namespace] is package
    assert sys.modules[f"{namespace}.child"] is child


async def test_cancel_after_candidate_import_removes_namespace(tmp_path: Path) -> None:
    class CancellingWorker(_InlineWorker):
        scope: anyio.CancelScope | None = None

        async def run_sync(
            self,
            function: Callable[P, T],
            /,
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> T:
            result = await run_in_thread(partial(function, *args, **kwargs))
            if function is drawing_loader._load_generation:
                assert self.scope is not None
                self.scope.cancel()
            return result

    source = tmp_path / "draw.py"
    source.write_text("def draw(canvas, request):\n    pass\n", encoding="utf-8")
    worker = CancellingWorker()
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source)}, worker=worker
    )
    before_modules = _owned_module_names()
    before_finders = _owned_finders()
    with anyio.CancelScope() as scope:
        worker.scope = scope
        await registry.reload("card")
        pytest.fail("pending cancellation should be delivered before installation")
    await registry.aclose()
    assert _owned_module_names() == before_modules
    assert _owned_finders() == before_finders


async def test_close_drains_active_lease_and_preserves_late_import(
    tmp_path: Path,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(
        "def draw(canvas, request):\n"
        "    from .helper import VALUE\n"
        "    canvas.append(VALUE)\n",
        encoding="utf-8",
    )
    (tmp_path / "helper.py").write_text("VALUE = 'alive'\n", encoding="utf-8")
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source)}, worker=_InlineWorker()
    )
    before = _owned_module_names()
    closing = anyio.Event()
    closed = anyio.Event()

    async def close() -> None:
        closing.set()
        await registry.aclose()
        closed.set()

    async with anyio.create_task_group() as group:
        async with registry.lease("card") as draw:
            group.start_soon(close)
            await closing.wait()
            await anyio.wait_all_tasks_blocked()
            assert not closed.is_set()
            canvas: list[str] = []
            draw(canvas, {})
            assert canvas == ["alive"]
        await closed.wait()
    assert _owned_module_names() == before


async def test_singleflight_and_independent_registry_namespaces(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)

    class CountingWorker(_InlineWorker):
        imports = 0

        async def run_sync(
            self,
            function: Callable[P, T],
            /,
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> T:
            if function is drawing_loader._load_generation:
                self.imports += 1

            def invoke() -> T:
                if function is drawing_loader._load_generation:
                    barrier.wait(timeout=5)
                return function(*args, **kwargs)

            return await run_in_thread(invoke)

    source = tmp_path / "draw.py"
    source.write_text("def draw(canvas, request):\n    pass\n", encoding="utf-8")
    worker = CountingWorker()
    registries = [
        DrawingRegistry(
            {"card": DrawingSpec("pillow", path=source, reload=True)}, worker=worker
        )
        for _ in range(2)
    ]
    before = _owned_finders()
    async with anyio.create_task_group() as group:
        for registry in registries:
            for _ in range(4):
                group.start_soon(_leased, registry, "card", [], {})
    assert worker.imports == 2
    assert len(_owned_finders()) == len(before) + 2
    await registries[0].aclose()
    await _leased(registries[1], "card", [], {})
    assert len(_owned_finders()) == len(before) + 1
    await registries[1].aclose()
    assert _owned_finders() == before


async def test_new_helper_package_replaces_previous_helper_module(
    tmp_path: Path,
) -> None:
    source = tmp_path / "draw.py"
    source.write_text(
        "from .helper import VALUE\n"
        "def draw(canvas, request):\n    canvas.append(VALUE)\n",
        encoding="utf-8",
    )
    (tmp_path / "helper.py").write_text("VALUE = 'module'\n", encoding="utf-8")
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source, reload=True)},
        worker=_InlineWorker(),
    )
    first: list[str] = []
    await _leased(registry, "card", first, {})
    package = tmp_path / "helper"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 'package'\n", encoding="utf-8")
    second: list[str] = []
    await _leased(registry, "card", second, {})
    assert first == ["module"]
    assert second == ["package"]
    await registry.aclose()


async def test_cancelled_close_can_retry_after_active_lease(tmp_path: Path) -> None:
    source = tmp_path / "draw.py"
    source.write_text("def draw(canvas, request):\n    pass\n", encoding="utf-8")
    registry = DrawingRegistry(
        {"card": DrawingSpec("pillow", path=source)}, worker=_InlineWorker()
    )
    before = _owned_module_names()
    entered = anyio.Event()
    release = anyio.Event()

    async def use() -> None:
        async with registry.lease("card"):
            entered.set()
            await release.wait()

    async with anyio.create_task_group() as group:
        group.start_soon(use)
        await entered.wait()
        with anyio.move_on_after(0) as cancelled:
            await registry.aclose()
        assert cancelled.cancel_called
        assert _owned_module_names() > before
        release.set()
        await registry.aclose()
    assert _owned_module_names() == before
