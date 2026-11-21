"""Contracts for executable documentation and public API imports."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "entari_plugin_htmlrender"
PACKAGE_ROOT = ROOT / "src" / PACKAGE
_PYTHON_FENCE = re.compile(
    r"(?ms)^(?P<indent>[ \t]*)```(?:python|py)(?:[^\n]*)\n"
    r"(?P<body>.*?)(?P=indent)```[ \t]*$"
)


def _python_sources() -> Iterator[tuple[Path, int, str]]:
    markdown_paths = (
        ROOT / "README.md",
        *sorted((ROOT / "docs").rglob("*.md")),
        *sorted((ROOT / "examples").rglob("*.md")),
    )
    for path in markdown_paths:
        text = path.read_text("utf-8")
        for match in _PYTHON_FENCE.finditer(text):
            yield (
                path.relative_to(ROOT),
                text.count("\n", 0, match.start("body")) + 1,
                textwrap.dedent(match.group("body")),
            )

    for path in sorted((ROOT / "examples").rglob("*.py")):
        yield path.relative_to(ROOT), 1, path.read_text("utf-8")


def _top_level_exports() -> frozenset[str]:
    tree = ast.parse((PACKAGE_ROOT / "__init__.py").read_text("utf-8"))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        )
    )
    return frozenset(ast.literal_eval(assignment.value))


def test_python_documentation_and_examples_parse() -> None:
    errors: list[str] = []
    for path, start_line, source in _python_sources():
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as error:
            line = start_line + (error.lineno or 1) - 1
            errors.append(f"{path}:{line}: {error.msg}")

    assert not errors, "Invalid Python examples:\n  " + "\n  ".join(errors)


def test_documented_package_imports_are_public() -> None:
    exports = _top_level_exports()
    errors: list[str] = []
    for path, start_line, source in _python_sources():
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module != PACKAGE:
                continue
            for alias in node.names:
                if alias.name not in exports:
                    line = start_line + node.lineno - 1
                    errors.append(f"{path}:{line}: {alias.name}")

    assert not errors, (
        f"Documentation imports names outside {PACKAGE}.__all__:\n  "
        + "\n  ".join(errors)
    )
