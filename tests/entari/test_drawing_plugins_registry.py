from __future__ import annotations

import asyncio
import importlib
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING, ParamSpec, TypeVar

import pytest

from entari_plugin_htmlrender.entari import drawing_plugins
from entari_plugin_htmlrender.entari.drawing_plugins import (
    EntariDrawingPool,
    EntariDrawingRegistry,
)
from entari_plugin_htmlrender.graphics.drawing_loader import (
    DrawingLoadError,
    DrawingNotFoundError,
    DrawingSpec,
)

# Import the adapter before Entari installs its plugin-aware import hook.
# isort: split
from arclet.entari.config import EntariConfig
from arclet.entari.plugin import (
    disable_plugin,
    find_plugin,
    load_plugin,
    reload_plugin,
    unload_plugin_async,
)
from arclet.entari.plugin.service import plugin_service
from arclet.letoderea.utils import set_event_loop

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path


_SETUP = """
import asyncio
import importlib
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from entari_plugin_htmlrender.entari.drawing_plugins import EntariDrawingPool
from entari_plugin_htmlrender.graphics.drawing_loader import DrawingSpec, DrawingLoadError
from arclet.entari.config import EntariConfig
from arclet.entari.plugin import find_plugin, load_plugin, reload_plugin, requires
from arclet.entari.plugin.service import plugin_service
from arclet.letoderea.utils import set_event_loop

class Worker:
    async def run_sync(self, function, /, *args, **kwargs):
        return function(*args, **kwargs)

async def value(registry, name):
    data = {}
    async with registry.lease(name) as draw:
        draw(None, data)
    return data['value']

async def exercise(base):
    set_event_loop(asyncio.get_running_loop())
    EntariConfig(base / 'entari.yml')
    worker = Worker()
    pool = EntariDrawingPool()
"""


def _run_isolated(body: str) -> None:
    source = (
        _SETUP
        + textwrap.indent(textwrap.dedent(body), "    ")
        + "\nwith TemporaryDirectory() as directory:\n"
        + "    asyncio.run(exercise(Path(directory)))\n"
    )
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and test source
        [sys.executable, "-c", source],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_entari_graph_reloads_helpers_and_follows_external_reloads() -> None:
    _run_isolated(
        """
        cards = base / 'probe_cards'
        cards.mkdir()
        (cards / '__init__.py').write_text('')
        helper = cards / 'helper.py'
        helper.write_text('def color():\\n    return 1\\n')
        (cards / 'a.py').write_text(
            'from .helper import color\\nCOMPUTED = color()\\n'
            'def draw(canvas, data):\\n    data["value"] = (color(), COMPUTED)\\n'
        )
        (cards / 'b.py').write_text(
            'from .helper import color\\n'
            'def draw(canvas, data):\\n    data["value"] = color()\\n'
        )
        original_path = list(sys.path)
        registry = pool.registry({
            'a': DrawingSpec('pillow', path=cards / 'a.py', reload=True),
            'b': DrawingSpec('pillow', path=cards / 'b.py'),
        }, worker=worker)
        assert find_plugin('probe_cards.a').module.color is find_plugin('probe_cards.b').module.color
        assert await value(registry, 'a') == (1, 1)
        helper.write_text('def color():\\n    return 222\\n')
        assert await value(registry, 'a') == (222, 222)
        assert await value(registry, 'b') == 222
        helper.write_text('this is invalid Python!\\n')
        assert await value(registry, 'a') == (222, 222)
        assert await value(registry, 'b') == 222
        try:
            await registry.reload('a')
        except DrawingLoadError:
            pass
        else:
            raise AssertionError('manual reload must report invalid helper')
        helper.write_text('def color():\\n    return 3333\\n')
        await registry.reload('a')
        assert await value(registry, 'a') == (3333, 3333)
        (cards / 'b.py').write_text('def draw(canvas, data):\\n    data["value"] = 999\\n')
        assert await reload_plugin('probe_cards.b')
        assert await value(registry, 'b') == 999
        await registry.aclose()
        assert not any(name.startswith('probe_cards') for name in plugin_service.plugins)
        assert sys.path == original_path
        """
    )


def test_shared_pool_preserves_borrowed_plugins_and_overlapping_generations() -> None:
    _run_isolated(
        """
        (base / 'borrowed.py').write_text('def draw(canvas, data):\\n    data["value"] = 7\\n')
        (base / 'removed.py').write_text('def draw(canvas, data):\\n    data["value"] = 8\\n')
        (base / 'shared.py').write_text('def draw(canvas, data):\\n    data["value"] = 9\\n')
        sys.path.insert(0, str(base))
        borrowed = load_plugin('borrowed').plugin
        first = pool.registry({
            name: DrawingSpec('pillow', module=name)
            for name in ('borrowed', 'removed', 'shared')
        }, worker=worker)
        shared = find_plugin('shared')
        second = pool.registry({
            name: DrawingSpec('pillow', module=name)
            for name in ('borrowed', 'shared')
        }, worker=worker)
        await first.aclose()
        assert find_plugin('removed') is None
        assert find_plugin('shared') is shared
        assert find_plugin('borrowed') is borrowed
        assert await value(second, 'shared') == 9
        await second.aclose()
        assert find_plugin('shared') is None
        assert find_plugin('borrowed') is borrowed
        assert str(base) in sys.path
        """
    )


def test_lazy_cycles_load_once_and_cleanup_waits_for_leases() -> None:
    _run_isolated(
        """
        (base / 'cycle_a.py').write_text(
            'import cycle_b\\nVALUE = 12\\n'
            'def draw(canvas, data):\\n    data["value"] = cycle_b.VALUE\\n'
        )
        (base / 'cycle_b.py').write_text(
            'import cycle_a\\nVALUE = 34\\n'
            'def draw(canvas, data):\\n    data["value"] = cycle_a.VALUE\\n'
        )
        registry = pool.registry({
            'a': DrawingSpec('pillow', path=base / 'cycle_a.py'),
            'b': DrawingSpec('pillow', path=base / 'cycle_b.py'),
        }, worker=worker)
        assert await value(registry, 'a') == 34
        assert await value(registry, 'b') == 12
        async with registry.lease('a'):
            closing = asyncio.create_task(registry.aclose())
            await asyncio.sleep(0)
            assert not closing.done()
            assert find_plugin('cycle_a') is not None
        await closing
        assert find_plugin('cycle_a') is None
        assert find_plugin('cycle_b') is None
        """
    )


def test_initial_failure_rolls_back_and_unmanaged_helper_has_clear_error() -> None:
    _run_isolated(
        """
        (base / 'valid.py').write_text('def draw(canvas, data):\\n    data["value"] = 1\\n')
        (base / 'invalid.py').write_text('not valid Python!\\n')
        original_path = list(sys.path)
        try:
            pool.registry({
                'good': DrawingSpec('pillow', path=base / 'valid.py'),
                'bad': DrawingSpec('pillow', path=base / 'invalid.py'),
            }, worker=worker)
        except DrawingLoadError:
            pass
        else:
            raise AssertionError('invalid initial source accepted')
        assert find_plugin('valid') is None
        assert find_plugin('invalid') is None
        assert sys.path == original_path
        (base / 'plain_helper.py').write_text('VALUE = 3\\n')
        (base / 'plain_consumer.py').write_text(
            'import plain_helper\\n'
            'def draw(canvas, data):\\n    data["value"] = plain_helper.VALUE\\n'
        )
        try:
            pool.registry({'plain': DrawingSpec('pillow', path=base / 'plain_consumer.py', reload=True)}, worker=worker)
        except DrawingLoadError as error:
            assert 'not managed by Entari' in str(error)
        else:
            raise AssertionError('unmanaged helper silently accepted for polling')
        assert find_plugin('plain_consumer') is None
        assert sys.path == original_path
        """
    )


_P = ParamSpec("_P")
_R = TypeVar("_R")


class _Worker:
    def __init__(self) -> None:
        self.calls = 0

    async def run_sync(
        self,
        function: Callable[_P, _R],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _R:
        self.calls += 1
        return function(*args, **kwargs)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[EntariDrawingPool]:

    monkeypatch.setattr(
        EntariConfig, "instance", getattr(EntariConfig, "instance", None), raising=False
    )
    monkeypatch.setattr(EntariConfig, "_inited", EntariConfig._inited)
    EntariConfig(tmp_path / "entari.yml")
    set_event_loop(asyncio.get_running_loop())
    result = EntariDrawingPool()
    try:
        yield result
    finally:
        await result.aclose()


async def _value(registry: EntariDrawingRegistry, name: str) -> object:
    data: dict[str, object] = {}
    async with registry.lease(name) as draw:
        draw(None, data)
    return data["value"]


def _write(directory: Path, name: str, source: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


async def test_direct_shared_helper_polling_and_failed_reload(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:

    package = tmp_path / "direct_cards"
    _write(package, "__init__.py", "")
    helper = _write(package, "helper.py", "def color():\n    return 1\n")
    a = _write(
        package,
        "a.py",
        "from .helper import color\nVALUE = color()\n"
        "def draw(canvas, data):\n    data['value'] = (VALUE, color())\n",
    )
    b = _write(
        package,
        "b.py",
        "from .helper import color\n"
        "def draw(canvas, data):\n    data['value'] = color()\n",
    )
    worker = _Worker()
    registry = pool.registry(
        {
            "a": DrawingSpec("pillow", path=a, reload=True),
            "b": DrawingSpec("pillow", path=b),
        },
        worker=worker,
    )
    assert registry.names == frozenset({"a", "b"})
    assert await _value(registry, "a") == (1, 1)
    helper.write_text("def color():\n    return 987\n", encoding="utf-8")
    assert await _value(registry, "a") == (987, 987)
    calls = worker.calls
    assert await _value(registry, "b") == 987
    assert worker.calls == calls
    helper.write_text("broken Python!\n", encoding="utf-8")
    assert await _value(registry, "a") == (987, 987)
    assert await _value(registry, "a") == (987, 987)
    with pytest.raises(DrawingLoadError, match="dependency"):
        await registry.reload("a")
    helper.write_text("def color():\n    return 456\n", encoding="utf-8")
    await registry.reload("a")
    assert await _value(registry, "a") == (456, 456)
    b.write_text("def draw(canvas, data):\n    data['value'] = 123\n", encoding="utf-8")
    assert await reload_plugin("direct_cards.b")
    assert await _value(registry, "b") == 123
    b.write_text("async def draw(canvas, data):\n    pass\n", encoding="utf-8")
    with pytest.raises(DrawingLoadError, match="synchronous"):
        await registry.reload("b")
    with pytest.raises(DrawingLoadError, match="synchronous"):
        await _value(registry, "b")
    await registry.aclose()
    assert find_plugin("direct_cards.a") is None
    assert find_plugin("direct_cards.helper") is None
    with pytest.raises(DrawingLoadError, match="closed"):
        await registry.reload("a")
    with pytest.raises(DrawingNotFoundError):
        registry.spec("missing")
    await registry.aclose()


async def test_direct_borrowed_plugins_and_config_overlap(
    pool: EntariDrawingPool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.syspath_prepend(str(tmp_path))
    names = ("direct_borrowed", "direct_retained", "direct_removed")
    for name in names:
        _write(
            tmp_path, f"{name}.py", "def draw(canvas, data):\n    data['value'] = 5\n"
        )
    borrowed = load_plugin("direct_borrowed").plugin
    try:
        first = pool.registry(
            {name: DrawingSpec("pillow", module=name) for name in names},
            worker=_Worker(),
        )
        second = pool.registry(
            {name: DrawingSpec("pillow", module=name) for name in names[:2]},
            worker=_Worker(),
        )
        await first.aclose()
        assert find_plugin("direct_removed") is None
        assert await _value(second, "direct_retained") == 5
        await second.aclose()
        assert find_plugin("direct_retained") is None
        assert find_plugin("direct_borrowed") is borrowed
        assert str(tmp_path) in sys.path
    finally:
        await unload_plugin_async("direct_borrowed")


async def test_direct_cycle_lease_drain_and_aliases(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:

    sources = {}
    for name, other, value in (("alpha", "beta", 1), ("beta", "alpha", 2)):
        sources[name] = _write(
            tmp_path,
            f"direct_{name}.py",
            f"import direct_{other}\nVALUE = {value}\n"
            f"def draw(canvas, data):\n    data['value'] = direct_{other}.VALUE\n",
        )
    registry = pool.registry(
        {
            **{
                name: DrawingSpec("pillow", path=path) for name, path in sources.items()
            },
            "alias": DrawingSpec("pillow", module="direct_alpha"),
        },
        worker=_Worker(),
    )
    assert await _value(registry, "alpha") == 2
    assert await _value(registry, "beta") == 1
    assert await _value(registry, "alias") == 2
    async with registry.lease("alpha"):
        closed = asyncio.create_task(registry.aclose())
        await asyncio.sleep(0)
        assert not closed.done()
    await closed
    assert find_plugin("direct_alpha") is None
    assert find_plugin("direct_beta") is None


async def test_direct_source_failures_rollback_mounts(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:

    original_path = list(sys.path)
    good = _write(tmp_path, "direct_good.py", "def draw(canvas, data):\n    pass\n")
    bad = _write(tmp_path, "direct_bad.py", "not valid Python!\n")
    with pytest.raises(DrawingLoadError, match="Could not load"):
        pool.registry(
            {
                "good": DrawingSpec("pillow", path=good),
                "bad": DrawingSpec("pillow", path=bad),
            },
            worker=_Worker(),
        )
    assert find_plugin("direct_good") is None
    assert sys.path == original_path
    cases = [
        DrawingSpec("pillow", path=tmp_path / "absent.py"),
        DrawingSpec("pillow", module="direct_does_not_exist"),
        DrawingSpec("pillow", module="math"),
        DrawingSpec("pillow", path=_write(tmp_path, "bad-name.py", "")),
        DrawingSpec("pillow", path=_write(tmp_path, "direct_no_draw.py", "VALUE=1\n")),
    ]
    for spec in cases:
        with pytest.raises(DrawingLoadError):
            pool.registry({"drawing": spec}, worker=_Worker())
        assert sys.path == original_path


async def test_direct_collisions_plain_imports_and_unmanaged_helpers(
    pool: EntariDrawingPool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    folder = tmp_path / "first"
    path = _write(folder, "direct_collision.py", "def draw(canvas, data):\n    pass\n")
    other = _write(tmp_path / "second", path.name, path.read_text(encoding="utf-8"))
    registry = pool.registry(
        {"one": DrawingSpec("pillow", path=path)}, worker=_Worker()
    )
    with pytest.raises(DrawingLoadError, match="different source"):
        pool.registry({"two": DrawingSpec("pillow", path=other)}, worker=_Worker())
    await registry.aclose()
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path, "direct_plain.py", "def draw(canvas, data):\n    pass\n")
    plain = importlib.import_module("direct_plain")
    try:
        with pytest.raises(DrawingLoadError, match="outside Entari"):
            pool.registry(
                {"plain": DrawingSpec("pillow", module="direct_plain")},
                worker=_Worker(),
            )
        assert sys.modules["direct_plain"] is plain
    finally:
        sys.modules.pop("direct_plain", None)
    _write(tmp_path, "direct_unmanaged.py", "VALUE = 1\n")
    consumer = _write(
        tmp_path,
        "direct_consumer.py",
        "import direct_unmanaged\n"
        "def draw(canvas, data):\n    data['value'] = direct_unmanaged.VALUE\n",
    )
    try:
        with pytest.raises(DrawingLoadError, match="not managed by Entari"):
            pool.registry(
                {"consumer": DrawingSpec("pillow", path=consumer, reload=True)},
                worker=_Worker(),
            )
        assert find_plugin("direct_consumer") is None
    finally:
        sys.modules.pop("direct_unmanaged", None)


async def test_cancelled_reload_finishes_swap_before_releasing_pool_lock(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:
    path = _write(
        tmp_path,
        "direct_cancelled.py",
        "import asyncio\n"
        "from arclet.entari.plugin import collect_disposes\n"
        "started = asyncio.Event()\nreleased = asyncio.Event()\n"
        "async def dispose():\n    started.set()\n    await released.wait()\n"
        "collect_disposes(dispose)\n"
        "def draw(canvas, data):\n    data['value'] = 1\n",
    )
    registry = pool.registry(
        {"drawing": DrawingSpec("pillow", path=path)}, worker=_Worker()
    )
    plugin = find_plugin("direct_cancelled")
    assert plugin is not None
    started: asyncio.Event = plugin.module.started
    released: asyncio.Event = plugin.module.released
    path.write_text(
        "def draw(canvas, data):\n    data['value'] = 222\n", encoding="utf-8"
    )
    reloading = asyncio.create_task(registry.reload("drawing"))
    waiting = asyncio.create_task(_value(registry, "drawing"))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        reloading.cancel()
        await asyncio.sleep(0)
        assert not reloading.done()
        await asyncio.sleep(0)
        assert not waiting.done()
        reloading.cancel()
    finally:
        released.set()
    with pytest.raises(asyncio.CancelledError):
        await reloading
    assert await waiting == 222
    assert "direct_cancelled" not in plugin_service._staged
    assert "direct_cancelled" not in plugin_service._staged_bindings
    assert find_plugin("direct_cancelled") is not None


async def test_polling_reloads_reverted_source_after_external_module_replacement(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:
    original = "def draw(canvas, data):\n    data['value'] = 1\n"
    path = _write(tmp_path, "direct_reverted.py", original)
    registry = pool.registry(
        {"drawing": DrawingSpec("pillow", path=path, reload=True)},
        worker=_Worker(),
    )
    assert await _value(registry, "drawing") == 1
    path.write_text(
        "def draw(canvas, data):\n    data['value'] = 222\n", encoding="utf-8"
    )
    assert await reload_plugin("direct_reverted")
    path.write_text(original, encoding="utf-8")
    assert await _value(registry, "drawing") == 1


async def test_borrowed_plugin_has_no_assumed_imported_source_baseline(
    pool: EntariDrawingPool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    path = _write(
        tmp_path,
        "direct_old_baseline.py",
        "def draw(canvas, data):\n    data['value'] = 222\n",
    )
    assert load_plugin("direct_old_baseline")
    try:
        path.write_text(
            "def draw(canvas, data):\n    data['value'] = 1\n", encoding="utf-8"
        )
        registry = pool.registry(
            {
                "drawing": DrawingSpec(
                    "pillow", module="direct_old_baseline", reload=True
                )
            },
            worker=_Worker(),
        )
        assert await _value(registry, "drawing") == 1
        await registry.aclose()
        assert find_plugin("direct_old_baseline") is not None
    finally:
        await unload_plugin_async("direct_old_baseline")


async def test_conflicting_source_aliases_rejected_before_imports_and_across_generations(
    pool: EntariDrawingPool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "direct_alias_cards"
    _write(package, "__init__.py", "")
    path = _write(
        package, "card.py", "def draw(canvas, data):\n    data['value'] = None\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.syspath_prepend(str(package))
    original_path = list(sys.path)
    definitions = {
        "file": DrawingSpec("pillow", path=path),
        "module": DrawingSpec("pillow", module="direct_alias_cards.card"),
    }
    with pytest.raises(DrawingLoadError, match="conflicting module names"):
        pool.registry(definitions, worker=_Worker())
    assert find_plugin("card") is None
    assert find_plugin("direct_alias_cards.card") is None
    assert "direct_alias_cards" not in sys.modules
    assert sys.path == original_path
    first = pool.registry({"file": definitions["file"]}, worker=_Worker())
    with pytest.raises(DrawingLoadError, match="conflicting module names"):
        pool.registry({"module": definitions["module"]}, worker=_Worker())
    assert find_plugin("direct_alias_cards.card") is None
    assert await _value(first, "file") is None


class _PausedWorker(_Worker):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.released = asyncio.Event()

    async def run_sync(
        self, function: Callable[_P, _R], /, *args: _P.args, **kwargs: _P.kwargs
    ) -> _R:
        self.started.set()
        await self.released.wait()
        return await super().run_sync(function, *args, **kwargs)


async def test_close_rejects_lease_waiting_for_refresh(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:
    path = _write(
        tmp_path,
        "direct_admission.py",
        "def draw(canvas, data):\n    data['value'] = 1\n",
    )
    worker = _PausedWorker()
    registry = pool.registry(
        {"drawing": DrawingSpec("pillow", path=path, reload=True)}, worker=worker
    )
    admitted = asyncio.create_task(_value(registry, "drawing"))
    await asyncio.wait_for(worker.started.wait(), timeout=2)
    closing = asyncio.create_task(registry.aclose())
    await asyncio.sleep(0)
    worker.released.set()
    with pytest.raises(DrawingLoadError, match="closed"):
        await admitted
    await closing
    assert registry._active == 0
    assert find_plugin("direct_admission") is None


async def test_close_retries_failed_unload_without_losing_bookkeeping(
    pool: EntariDrawingPool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, "direct_retry.py", "def draw(canvas, data):\n    pass\n")
    original_path = list(sys.path)
    registry = pool.registry(
        {"drawing": DrawingSpec("pillow", path=path)}, worker=_Worker()
    )
    native_unload = drawing_plugins.unload_plugin_async
    calls = 0

    async def fail_once(name: str) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("cleanup failed")
        return await native_unload(name)

    monkeypatch.setattr(drawing_plugins, "unload_plugin_async", fail_once)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await registry.aclose()
    assert not registry._closed
    assert registry in pool._registries
    assert registry._roots
    assert registry._claimed == {"direct_retry"}
    assert "direct_retry" in pool._owned
    assert find_plugin("direct_retry") is not None
    assert str(tmp_path) in sys.path
    with pytest.raises(DrawingLoadError, match="closed"):
        await _value(registry, "drawing")
    await registry.aclose()
    assert calls == 2
    assert registry._closed
    assert registry not in pool._registries
    assert find_plugin("direct_retry") is None
    assert sys.path == original_path


async def test_external_consumer_retains_mount_until_pool_can_release_plugin(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:
    original_path = list(sys.path)
    path = _write(
        tmp_path,
        "direct_retained_mount.py",
        "def draw(canvas, data):\n    data['value'] = 1\n",
    )
    _write(
        tmp_path,
        "direct_external_mount.py",
        "from direct_retained_mount import draw\n",
    )
    registry = pool.registry(
        {"drawing": DrawingSpec("pillow", path=path)}, worker=_Worker()
    )
    assert load_plugin("direct_external_mount")
    try:
        await registry.aclose()
        assert find_plugin("direct_retained_mount") is not None
        assert str(tmp_path) in sys.path
        path.write_text(
            "def draw(canvas, data):\n    data['value'] = 222\n", encoding="utf-8"
        )
        assert await reload_plugin("direct_retained_mount")
        external = find_plugin("direct_external_mount")
        assert external is not None
        data: dict[str, object] = {}
        external.module.draw(None, data)
        assert data["value"] == 222
        await pool.aclose()
        assert str(tmp_path) in sys.path
    finally:
        await unload_plugin_async("direct_external_mount")
    await pool.aclose()
    assert find_plugin("direct_retained_mount") is None
    assert sys.path == original_path


async def test_registry_rejects_disabled_or_unloaded_canonical_plugin(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:
    path = _write(
        tmp_path,
        "direct_availability.py",
        "def draw(canvas, data):\n    data['value'] = 1\n",
    )
    registry = pool.registry(
        {"drawing": DrawingSpec("pillow", path=path)}, worker=_Worker()
    )
    assert await _value(registry, "drawing") == 1
    assert await disable_plugin("direct_availability")
    with pytest.raises(DrawingLoadError, match="not available"):
        await _value(registry, "drawing")
    await unload_plugin_async("direct_availability")
    with pytest.raises(DrawingLoadError, match="not available"):
        await _value(registry, "drawing")


async def test_nested_package_helpers_reload_independently_without_churn(
    pool: EntariDrawingPool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "direct_nested_cards"
    _write(package, "__init__.py", "")
    constants = _write(package, "constants.py", "def value():\n    return 1\n")
    palette_source = (
        "from .constants import value\nPALETTE = value()\n"
        "def color():\n    return PALETTE\n"
    )
    palette = _write(package, "palette.py", palette_source)
    _write(package, "unrelated.py", "raise AssertionError('must stay unloaded')\n")
    _write(package, "bad-name.py", "raise AssertionError('invalid module name')\n")
    _write(
        package / "bad-dir", "hidden.py", "raise AssertionError('invalid directory')\n"
    )
    _write(
        package / "__pycache__",
        "hidden.py",
        "raise AssertionError('cache directory')\n",
    )
    paths = {
        name: _write(
            package,
            f"{name}.py",
            "from .palette import color\nCOMPUTED = color()\n"
            "def draw(canvas, data):\n    data['value'] = (COMPUTED, color())\n",
        )
        for name in ("profile", "second")
    }
    registry = pool.registry(
        {
            name: DrawingSpec("pillow", path=path, reload=True)
            for name, path in paths.items()
        },
        worker=_Worker(),
    )
    assert await _value(registry, "profile") == (1, 1)
    assert await _value(registry, "second") == (1, 1)
    assert "direct_nested_cards.unrelated" in registry._declared
    assert "direct_nested_cards.unrelated" not in sys.modules
    assert not any(
        "bad-" in name or "__pycache__" in name for name in registry._declared
    )
    assert not any(
        name.startswith("direct_nested_cards") for name in plugin_service._subplugined
    )
    profile = find_plugin("direct_nested_cards.profile")
    second = find_plugin("direct_nested_cards.second")
    assert profile is not None and second is not None
    assert profile.module.color is second.module.color
    calls: list[str] = []
    native_reload = drawing_plugins.reload_plugin

    async def recording_reload(module: str) -> object:
        calls.append(module)
        return await native_reload(module)

    monkeypatch.setattr(drawing_plugins, "reload_plugin", recording_reload)
    constants.write_text("def value():\n    return 222\n", encoding="utf-8")
    palette.write_text(palette_source + "EXTRA = 7\n", encoding="utf-8")
    assert await _value(registry, "profile") == (222, 222)
    assert calls == ["direct_nested_cards.constants"]
    stable = {
        name: plugin.module
        for name, plugin in plugin_service.plugins.items()
        if name.startswith("direct_nested_cards")
    }
    assert await _value(registry, "second") == (222, 222)
    assert await _value(registry, "profile") == (222, 222)
    assert calls == ["direct_nested_cards.constants"]
    assert all(
        plugin_service.plugins[name].module is module for name, module in stable.items()
    )
    constants.write_text("broken Python!\n", encoding="utf-8")
    assert await _value(registry, "profile") == (222, 222)
    assert await _value(registry, "second") == (222, 222)
    with pytest.raises(DrawingLoadError, match="dependency"):
        await registry.reload("profile")
    assert all(
        plugin_service.plugins[name].module is module for name, module in stable.items()
    )
    await registry.aclose()
    assert not any(
        name.startswith("direct_nested_cards") for name in plugin_service.plugins
    )


async def test_refresh_declares_new_helper_before_altered_drawing_imports_it(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:
    package = tmp_path / "direct_added_cards"
    _write(package, "__init__.py", "")
    path = _write(
        package, "profile.py", "def draw(canvas, data):\n    data['value'] = 1\n"
    )
    registry = pool.registry(
        {"profile": DrawingSpec("pillow", path=path, reload=True)}, worker=_Worker()
    )
    _write(package, "new_helper.py", "def value():\n    return 222\n")
    path.write_text(
        "from .new_helper import value\nCOMPUTED = value()\n"
        "def draw(canvas, data):\n    data['value'] = COMPUTED\n",
        encoding="utf-8",
    )
    assert await _value(registry, "profile") == 222
    helper = find_plugin("direct_added_cards.new_helper")
    profile = find_plugin("direct_added_cards.profile")
    assert helper is not None and profile is not None
    assert "direct_added_cards.new_helper" not in plugin_service._subplugined
    assert await _value(registry, "profile") == 222
    assert find_plugin("direct_added_cards.new_helper") is helper
    assert find_plugin("direct_added_cards.profile") is profile
    await registry.aclose()
    assert find_plugin("direct_added_cards.new_helper") is None


@pytest.mark.parametrize("polling", [False, True])
async def test_new_lazy_helper_is_declared_and_owned_before_drawing_call(
    pool: EntariDrawingPool, tmp_path: Path, *, polling: bool
) -> None:
    package = tmp_path / "direct_lazy_cards"
    _write(package, "__init__.py", "")
    path = _write(
        package,
        "profile.py",
        "def draw(canvas, data):\n    from .new_helper import value\n    data['value'] = value()\n",
    )
    registry = pool.registry(
        {"profile": DrawingSpec("pillow", path=path, reload=polling)}, worker=_Worker()
    )
    _write(package, "new_helper.py", "def value():\n    return 222\n")
    assert find_plugin("direct_lazy_cards.new_helper") is None
    assert await _value(registry, "profile") == 222
    assert "direct_lazy_cards.new_helper" not in plugin_service._subplugined
    assert "direct_lazy_cards.new_helper" in pool._owned
    await registry.aclose()
    assert not any(
        name.startswith("direct_lazy_cards") for name in plugin_service.plugins
    )


async def test_borrowed_package_subplugins_are_preserved_and_reload_reports_constraint(
    pool: EntariDrawingPool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "direct_native_package"
    _write(package, "__init__.py", "from . import palette\n")
    _write(package, "palette.py", "from .constants import value\nPALETTE = value()\n")
    _write(package, "constants.py", "def value():\n    return 1\n")
    path = _write(
        package,
        "profile.py",
        "from .palette import PALETTE\n"
        "def draw(canvas, data):\n    data['value'] = PALETTE\n",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert load_plugin("direct_native_package")
    stable = {
        name: plugin.module
        for name, plugin in plugin_service.plugins.items()
        if name.startswith("direct_native_package")
    }
    assert (
        plugin_service._subplugined["direct_native_package.palette"]
        == "direct_native_package"
    )
    try:
        with pytest.raises(DrawingLoadError, match="already an Entari subplugin"):
            pool.registry(
                {"profile": DrawingSpec("pillow", path=path, reload=True)},
                worker=_Worker(),
            )
        assert find_plugin("direct_native_package.profile") is None
        assert all(
            plugin_service.plugins[name].module is module
            for name, module in stable.items()
        )
        registry = pool.registry(
            {"profile": DrawingSpec("pillow", path=path)}, worker=_Worker()
        )
        assert await _value(registry, "profile") == 1
        with pytest.raises(DrawingLoadError, match="independent package modules"):
            await registry.reload("profile")
        await registry.aclose()
        assert all(
            plugin_service.plugins[name].module is module
            for name, module in stable.items()
        )
    finally:
        await unload_plugin_async("direct_native_package")


async def test_package_initializer_under_namespace_declares_only_real_subtree(
    pool: EntariDrawingPool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    namespace = tmp_path / "direct_namespace"
    package = namespace / "cards"
    _write(namespace, "unrelated.py", "raise AssertionError('namespace sibling')\n")
    _write(package, "helper.py", "def value():\n    return 1\n")
    _write(package / "nested", "unrelated.py", "raise AssertionError('not imported')\n")
    _write(
        package,
        "__init__.py",
        "def draw(canvas, data):\n    from .helper import value\n"
        "    data['value'] = value()\n",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = pool.registry(
        {
            "profile": DrawingSpec(
                "pillow", module="direct_namespace.cards", reload=True
            )
        },
        worker=_Worker(),
    )
    try:
        assert await _value(registry, "profile") == 1
        assert "direct_namespace.cards.helper" in registry._declared
        assert "direct_namespace.cards.nested.unrelated" in registry._declared
        assert "direct_namespace.unrelated" not in registry._declared
        assert "direct_namespace.cards.nested.unrelated" not in sys.modules
        assert "direct_namespace.cards.helper" not in plugin_service._subplugined
        await registry.aclose()
        assert not any(
            name.startswith("direct_namespace.cards") for name in plugin_service.plugins
        )
    finally:
        sys.modules.pop("direct_namespace", None)


async def test_eager_initializer_helpers_report_constraint_and_roll_back(
    pool: EntariDrawingPool, tmp_path: Path
) -> None:
    package = tmp_path / "direct_eager_package"
    _write(package, "helper.py", "VALUE = 1\n")
    path = _write(
        package,
        "__init__.py",
        "from .helper import VALUE\n"
        "def draw(canvas, data):\n    data['value'] = VALUE\n",
    )
    original_path = list(sys.path)
    with pytest.raises(DrawingLoadError, match="free of eager local helper imports"):
        pool.registry(
            {"profile": DrawingSpec("pillow", path=path, reload=True)}, worker=_Worker()
        )
    assert not any(
        name.startswith("direct_eager_package") for name in plugin_service.plugins
    )
    assert sys.path == original_path
