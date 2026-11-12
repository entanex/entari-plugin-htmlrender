from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import textwrap

_SETUP = r"""
import asyncio
from io import BytesIO
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PIL import Image
from arclet.entari.config import EntariConfig
from arclet.entari.plugin import find_plugin, load_plugin, reload_plugin, unload_plugin_async
from arclet.letoderea.utils import set_event_loop

directory = TemporaryDirectory()
root = Path(directory.name)
os.chdir(root)
sys.path.insert(0, str(root))
EntariConfig(root / "entari.yml")

def write(name, source):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path

def config(*names):
    return {"graphics": {"drawings": {
        name: {"backend": "pillow", "module": name} for name in names
    }}}

async def pixel(drawings, name):
    image = await drawings.render(name, width=2, height=2)
    with Image.open(BytesIO(bytes(image))) as decoded:
        return decoded.convert("RGB").getpixel((0, 0))
"""


def _run_isolated(body: str) -> None:
    source = (
        _SETUP
        + f"\nproject = Path({str(Path(__file__).resolve().parents[2])!r})\n"
        + "\nasync def main():\n    set_event_loop(asyncio.get_running_loop())\n"
        + textwrap.indent(textwrap.dedent(body), "    ")
        + "\nasyncio.run(main())\n"
    )
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and test source
        [sys.executable, "-c", source],
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_framework_dependencies_refresh_shared_helpers_and_computed_values() -> None:
    _run_isolated(
        r"""
        write("cards/__init__.py", "")
        helper = write("cards/palette.py", "def color():\n    return 'red'\n")
        write("cards/profile.py",
            "from .palette import color\n"
            "COLOR = color()\n"
            "def draw(canvas, data):\n"
            "    canvas.image.paste(COLOR, (0, 0, canvas.width, canvas.height))\n")
        write("cards/badge.py",
            "from .palette import color\n"
            "def draw(canvas, data):\n"
            "    canvas.image.paste(color(), (0, 0, canvas.width, canvas.height))\n")
        loaded = load_plugin("entari_plugin_htmlrender", {
            "graphics": {"drawings": {
                "profile": {"backend": "pillow", "module": "cards.profile", "reload": True},
                "badge": {"backend": "pillow", "module": "cards.badge"},
            }}
        })
        assert loaded, loaded
        from entari_plugin_htmlrender.graphics import DrawingLoadError
        drawings = loaded.plugin._services["htmlrender.runtime"].drawings
        try:
            assert await pixel(drawings, "profile") == (255, 0, 0)
            assert await pixel(drawings, "badge") == (255, 0, 0)
            first = find_plugin("cards.profile")
            assert first.module.color is find_plugin("cards.badge").module.color
            assert find_plugin("cards.palette") is not None
            helper.write_text("def color():\n    return 'blue'\n", encoding="utf-8")
            assert await pixel(drawings, "profile") == (0, 0, 255)
            assert await pixel(drawings, "badge") == (0, 0, 255)
            assert find_plugin("cards.profile") is not first
            assert find_plugin("cards.profile").module.color is find_plugin("cards.badge").module.color
            helper.write_text("def color(:\n", encoding="utf-8")
            assert await pixel(drawings, "profile") == (0, 0, 255)
            assert await pixel(drawings, "badge") == (0, 0, 255)
            try:
                await drawings.reload("profile")
            except DrawingLoadError:
                pass
            else:
                raise AssertionError("manual reload must report the invalid dependency")
            helper.write_text("def color():\n    return 'green'\n", encoding="utf-8")
            assert await pixel(drawings, "profile") == (0, 128, 0)
            assert await pixel(drawings, "badge") == (0, 128, 0)
            # Native external reload must be visible with polling disabled.
            write("cards/badge.py",
                "def draw(canvas, data):\n"
                "    canvas.image.paste('white', (0, 0, canvas.width, canvas.height))\n")
            result = await reload_plugin("cards.badge")
            assert result, result
            assert await pixel(drawings, "badge") == (255, 255, 255)
        finally:
            assert await unload_plugin_async("entari_plugin_htmlrender")
        assert find_plugin("cards.profile") is None
        assert find_plugin("cards.badge") is None
        assert find_plugin("cards.palette") is None
        """
    )


def test_mutual_imports_use_one_canonical_module_per_source() -> None:
    _run_isolated(
        r"""
        for name, other, color in [("first", "second", "red"), ("second", "first", "blue")]:
            write(f"{name}.py",
                f"import {other}\n"
                f"def color():\n    return '{color}'\n"
                f"def draw(canvas, data):\n    canvas.image.paste({other}.color(), (0, 0, canvas.width, canvas.height))\n")
        loaded = load_plugin("entari_plugin_htmlrender", {
            "graphics": {"drawings": {
                "first": {"backend": "pillow", "path": str(root / "first.py")},
                "second": {"backend": "pillow", "module": "second"},
                "alias": {"backend": "pillow", "module": "first"},
            }}
        })
        assert loaded, loaded
        drawings = loaded.plugin._services["htmlrender.runtime"].drawings
        try:
            for name, expected in [("first", (0, 0, 255)), ("second", (255, 0, 0)), ("alias", (0, 0, 255))]:
                assert await pixel(drawings, name) == expected
            assert find_plugin("first").module.second.color is find_plugin("second").module.color
            assert find_plugin("second").module.first.color is find_plugin("first").module.color
        finally:
            assert await unload_plugin_async("entari_plugin_htmlrender")
        assert find_plugin("first") is None
        assert find_plugin("second") is None
        """
    )


def test_config_reload_releases_removed_sources_and_preserves_borrowed_plugins() -> (
    None
):
    _run_isolated(
        r"""
        for name in ("owned", "retained", "borrowed"):
            write(f"{name}.py", "def draw(canvas, data):\n    pass\n")
        borrowed = load_plugin("borrowed").plugin
        loaded = load_plugin("entari_plugin_htmlrender", config("owned", "retained", "borrowed"))
        assert loaded, loaded
        old_service = loaded.plugin._services["htmlrender.runtime"]
        for name in ("owned", "retained", "borrowed"):
            await old_service.drawings.render(name, width=2, height=2)
        retained = find_plugin("retained")
        result = await reload_plugin("entari_plugin_htmlrender", config("retained", "borrowed"))
        assert result, result
        service = result.plugin._services["htmlrender.runtime"]
        assert service is not old_service
        assert service.drawings.names == frozenset({"retained", "borrowed"})
        assert find_plugin("owned") is None
        assert find_plugin("retained") is retained
        assert find_plugin("borrowed") is borrowed
        await service.drawings.render("retained", width=2, height=2)
        assert await unload_plugin_async("entari_plugin_htmlrender")
        assert find_plugin("retained") is None
        assert find_plugin("borrowed") is borrowed
        assert await unload_plugin_async("borrowed")
        """
    )


def test_shipped_shared_package_example_loads_and_reloads_in_entari() -> None:
    _run_isolated(
        r"""
        import shutil

        package = root / "shared_cards"
        shutil.copytree(
            project / "examples/graphics_render/shared_cards",
            package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        loaded = load_plugin("entari_plugin_htmlrender", {
            "graphics": {"drawings": {
                "profile": {"backend": "pillow", "module": "shared_cards.profile", "reload": True},
                "badge": {"backend": "pillow", "module": "shared_cards.badge"},
            }}
        })
        assert loaded, loaded
        drawings = loaded.plugin._services["htmlrender.runtime"].drawings
        try:
            before = {}
            for name in ("profile", "badge"):
                image = await drawings.render(name, {"name": "Ada"}, width=640, height=360)
                assert (image.width, image.height) == (640, 360)
                before[name] = bytes(image)
            assert find_plugin("shared_cards.profile").module.card is find_plugin("shared_cards.badge").module.card
            colors = package / "colors.py"
            source = colors.read_text(encoding="utf-8")
            updated = source.replace("(30, 41, 59, 255)", "(60, 81, 99, 255)")
            assert updated != source
            colors.write_text(updated, encoding="utf-8")
            for name in ("profile", "badge"):
                image = await drawings.render(name, {"name": "Ada"}, width=640, height=360)
                assert bytes(image) != before[name]
        finally:
            assert await unload_plugin_async("entari_plugin_htmlrender")
        assert find_plugin("shared_cards.colors") is None
        """
    )
