"""Contracts keeping documentation aligned with the public API."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "entari_plugin_htmlrender"
PACKAGE_ROOT = ROOT / "src" / PACKAGE
SETTINGS_PATH = PACKAGE_ROOT / "config.py"
RUNTIME_CAPABILITIES_PATH = PACKAGE_ROOT / "runtime" / "capabilities.py"
MERMAID_RUNTIME_PATH = (
    ROOT / "docs" / "assets" / "javascripts" / "mermaid-11.16.0.min.js"
)
MERMAID_LICENSE_PATH = ROOT / "docs" / "assets" / "licenses" / "mermaid-11.16.0.txt"
MERMAID_RUNTIME_SHA256 = (
    "74d7c46dabca328c2294733910a8aa1ed0c37451776e8d5295da38a2b758fb9b"
)

DOCUMENTATION_ROOTS: Mapping[str, Path] = {
    "architecture": ROOT / "docs" / "extensions",
    "configuration": ROOT / "docs" / "configuration",
}

DOCUMENTATION_CHAPTERS = (
    ("开始使用", "start"),
    ("使用指南", "guides"),
    ("配置与部署", "configuration"),
    ("API 参考", "reference"),
    ("扩展开发", "extensions"),
    ("维护者指南", "project"),
)

EXPECTED_CONFIG_PATHS = frozenset(
    {
        "graphics.backend",
        "graphics.max_commands",
        "graphics.max_concurrency",
        "graphics.max_pixels",
        "html.max_auto_height",
        "html.max_concurrency",
        "html.max_device_pixel_ratio",
        "html.max_output_bytes",
        "html.max_pixels",
        "html.max_source_bytes",
        "observability.prometheus",
        "observability.sentry",
        "provider",
        "provider_config",
        "resources.cache.max_bytes",
        "resources.cache.max_entries",
        "resources.cache.max_resource_bytes",
        "resources.cache.revalidate_seconds",
        "resources.filehost.bind_host",
        "resources.filehost.bind_port",
        "resources.filehost.cache_ttl_seconds",
        "resources.filehost.max_bytes",
        "resources.filehost.max_entries",
        "resources.filehost.prewarm_enabled",
        "resources.filehost.prewarm_extensions",
        "resources.filehost.prewarm_max_files",
        "resources.filehost.prewarm_paths",
        "resources.filehost.public_base_url",
        "resources.filehost.request_header_name",
        "resources.filehost.request_header_salt",
        "resources.filehost.request_header_value",
        "resources.local_access.allow_any_path",
        "resources.local_access.allowed_paths",
        "resources.remote_access.allow_hosts",
        "resources.remote_access.allow_private_networks",
        "resources.remote_access.deny_hosts",
        "resources.remote_access.max_concurrent_fetches",
        "resources.remote_access.max_redirects",
        "resources.remote_access.request_timeout_seconds",
        "resources.templates.environment_cache_max_entries",
        "resources.templates.environment_compiled_cache_size",
        "resources.traversal.max_concurrency",
        "resources.traversal.max_depth",
        "resources.traversal.max_nodes",
        "startup",
    }
)

EXPECTED_ARCHITECTURE_TERMS = frozenset(
    {
        "AssetPublisher",
        "CapabilityCatalog",
        "ExecutionLeaseProvider",
        "HtmlRenderer",
        "LocalAccessPolicy",
        "ProviderBinding",
        "ProviderDependencies",
        "ProviderResourceAccess",
        "RenderProvider",
        "ResourceAccess",
        "ResourceContent",
        "ResourceFetcher",
        "ResourceMaterializer",
        "ResourceRef",
        "ResourceService",
        "ResourceStrategy",
        "TemplateRenderer",
        "WorkerExecutor",
    }
)

_PYTHON_FENCE = re.compile(
    r"(?ms)^(?P<indent>[ \t]*)```(?:python|py)(?:[^\n]*)\n"
    r"(?P<body>.*?)(?P=indent)```[ \t]*$"
)
_MARKDOWN_FENCE = re.compile(r"^[ \t]*(?P<marker>`{3,}|~{3,})")
_MARKDOWN_LEFT_BLOCK_BOUNDARY = re.compile(
    r"^[ \t]*(?:#{1,6}(?:\s|$)|(?:!!!|\?\?\?)\s+|>|\||<|\{[^}]*\}\s*$)"
)
_MARKDOWN_RIGHT_BLOCK_BOUNDARY = re.compile(
    r"^[ \t]*(?:"
    r"#{1,6}(?:\s|$)|[-+*]\s+|\d+[.)]\s+|(?:!!!|\?\?\?)\s+|>|\||"
    r":\s+|\[\^[^]]+\]:|\[[^]]+\]:|<|\{[^}]*\}\s*$"
    r")"
)
_MARKDOWN_THEMATIC_BREAK = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,})\s*$")
_CJK_CHARACTER = re.compile(
    r"[\u2e80-\u2eff\u3000-\u303f\u3040-\u30ff\u31c0-\u31ef"
    r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]"
)


@dataclass(frozen=True)
class PythonSource:
    path: Path
    lineno: int
    source: str


def _relative(path: Path) -> Path:
    return path.relative_to(ROOT)


def _documentation_files() -> list[Path]:
    files = [ROOT / "README.md"]
    files.extend(sorted((ROOT / "docs").rglob("*.md")))
    for path in sorted((ROOT / "examples").rglob("*")):
        if not path.is_file():
            continue
        if any(part in {".venv", "__pycache__"} for part in path.parts):
            continue
        if path.suffix in {
            ".md",
            ".py",
            ".toml",
            ".yaml",
            ".yml",
        } or path.name.startswith(".env"):
            files.append(path)
    return files


def _literal_string_sequence(path: Path, name: str) -> tuple[str, ...]:
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            matches = any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            matches = isinstance(node.target, ast.Name) and node.target.id == name
            value_node = node.value
        else:
            continue
        if not matches or value_node is None:
            continue
        value = ast.literal_eval(value_node)
        if isinstance(value, (list, tuple)) and all(
            isinstance(item, str) for item in value
        ):
            return tuple(value)
    raise AssertionError(f"{path} must define a literal string sequence {name}")


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _cjk_soft_break_occurrences(path: Path) -> list[str]:
    lines = path.read_text("utf-8").splitlines()
    occurrences: list[str] = []
    in_front_matter = bool(lines and lines[0].strip() == "---")
    fence_marker: str | None = None
    previous: str | None = None

    for lineno, line in enumerate(lines, start=1):
        if lineno == 1 and in_front_matter:
            continue
        if in_front_matter:
            if line.strip() == "---":
                in_front_matter = False
            continue

        fence = _MARKDOWN_FENCE.match(line)
        if fence_marker is not None:
            if (
                fence is not None
                and fence.group("marker").startswith(fence_marker[0])
                and len(fence.group("marker")) >= len(fence_marker)
            ):
                fence_marker = None
            previous = None
            continue
        if fence is not None:
            fence_marker = fence.group("marker")
            previous = None
            continue

        if previous is not None:
            left = previous.rstrip()
            right = line.lstrip()
            is_soft_break = bool(
                left
                and right
                and not previous.endswith(("  ", "\\"))
                and _MARKDOWN_LEFT_BLOCK_BOUNDARY.match(previous) is None
                and _MARKDOWN_RIGHT_BLOCK_BOUNDARY.match(line) is None
                and _MARKDOWN_THEMATIC_BREAK.match(previous) is None
                and _MARKDOWN_THEMATIC_BREAK.match(line) is None
            )
            if is_soft_break and (
                _CJK_CHARACTER.match(left[-1]) or _CJK_CHARACTER.match(right[0])
            ):
                occurrences.append(f"{_relative(path)}:{lineno - 1}")
        previous = line if line.strip() else None

    return occurrences


def test_canonical_documentation_roots_exist() -> None:
    missing_roots = [
        name for name, path in DOCUMENTATION_ROOTS.items() if not path.is_dir()
    ]
    assert not missing_roots, "Canonical documentation roots are missing: " + ", ".join(
        missing_roots
    )


def test_documentation_navigation_matches_the_reader_task_tree() -> None:
    navigation = (ROOT / "mkdocs.yml").read_text("utf-8").partition("\nnav:\n")[2]
    top_level = tuple(
        match.group("title")
        for match in re.finditer(r"(?m)^  - (?P<title>[^:]+):", navigation)
    )
    assert top_level == ("首页", *(title for title, _ in DOCUMENTATION_CHAPTERS))

    navigated_pages = tuple(
        match.group("path")
        for match in re.finditer(
            r"(?m)^\s+- [^:]+: (?P<path>\S+\.md)$",
            navigation,
        )
    )
    canonical_pages = {"index.md"}
    for _, directory in DOCUMENTATION_CHAPTERS:
        canonical_pages.update(
            str(path.relative_to(ROOT / "docs"))
            for path in (ROOT / "docs" / directory).rglob("*.md")
        )
    page_counts = Counter(navigated_pages)
    duplicate_pages = sorted(path for path, count in page_counts.items() if count > 1)
    assert not duplicate_pages, (
        "Pages appear more than once in navigation: " + ", ".join(duplicate_pages)
    )
    assert frozenset(navigated_pages) == frozenset(canonical_pages)

    legacy_pages = tuple(
        path.relative_to(ROOT)
        for directory in ("users", "maintainers")
        for path in (ROOT / "docs" / directory).rglob("*.md")
    )
    assert not legacy_pages


def test_documentation_has_no_cjk_prose_soft_breaks() -> None:
    occurrences = [
        occurrence
        for path in _documentation_files()
        if path.suffix == ".md"
        for occurrence in _cjk_soft_break_occurrences(path)
    ]
    assert not occurrences, (
        "CJK prose must not use Markdown soft line breaks:\n  "
        + "\n  ".join(occurrences)
    )


def _python_sources() -> Iterator[PythonSource]:
    markdown_paths = [ROOT / "README.md"]
    markdown_paths.extend(sorted((ROOT / "docs").rglob("*.md")))
    markdown_paths.extend(sorted((ROOT / "examples").rglob("*.md")))
    for path in markdown_paths:
        text = path.read_text("utf-8")
        for match in _PYTHON_FENCE.finditer(text):
            yield PythonSource(
                path=_relative(path),
                lineno=_line_number(text, match.start("body")),
                source=textwrap.dedent(match.group("body")),
            )
    for path in sorted((ROOT / "examples").rglob("*.py")):
        if any(part in {".venv", "__pycache__"} for part in path.parts):
            continue
        yield PythonSource(
            path=_relative(path),
            lineno=1,
            source=path.read_text("utf-8"),
        )


def _parse_python_source(
    source: PythonSource,
) -> tuple[ast.Module | None, str | None]:
    try:
        return ast.parse(source.source, filename=str(source.path)), None
    except SyntaxError as error:
        lineno = source.lineno + (error.lineno or 1) - 1
        return None, f"{source.path}:{lineno}: {error.msg}"


def _parse_python_sources() -> tuple[list[tuple[PythonSource, ast.Module]], list[str]]:
    parsed: list[tuple[PythonSource, ast.Module]] = []
    errors: list[str] = []
    for source in _python_sources():
        tree, error = _parse_python_source(source)
        if tree is not None:
            parsed.append((source, tree))
        if error is not None:
            errors.append(error)
    return parsed, errors


def test_python_examples_and_documentation_fences_parse() -> None:
    _, errors = _parse_python_sources()
    assert not errors, "Invalid Python examples:\n  " + "\n  ".join(errors)


def test_mermaid_runtime_is_pinned_and_self_hosted() -> None:
    config = (ROOT / "mkdocs.yml").read_text("utf-8")
    runtime = MERMAID_RUNTIME_PATH.read_bytes()
    license_text = MERMAID_LICENSE_PATH.read_text("utf-8")

    assert "assets/javascripts/mermaid-11.16.0.min.js" in config
    assert "name: mermaid" in config
    assert sha256(runtime).hexdigest() == MERMAID_RUNTIME_SHA256
    assert b'globalThis["mermaid"]' in runtime
    assert "The MIT License (MIT)" in license_text


def _top_level_exports() -> frozenset[str]:
    return frozenset(_literal_string_sequence(PACKAGE_ROOT / "__init__.py", "__all__"))


def test_curated_root_surface_is_fully_documented() -> None:
    exports = _top_level_exports() - {"__version__"}
    current_text = "\n".join(path.read_text("utf-8") for path in _documentation_files())
    missing = sorted(
        symbol
        for symbol in exports
        if re.search(rf"\b{re.escape(symbol)}\b", current_text) is None
    )
    assert not missing, "Current docs omit root symbols: " + ", ".join(missing)


def _runtime_capability_properties() -> frozenset[str]:
    tree = ast.parse(
        RUNTIME_CAPABILITIES_PATH.read_text("utf-8"),
        filename=str(RUNTIME_CAPABILITIES_PATH),
    )
    capability_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeCapabilities"
    )
    return frozenset(
        node.name
        for node in capability_class.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Name) and decorator.id == "property"
            for decorator in node.decorator_list
        )
    )


def test_first_party_capabilities_are_documented() -> None:
    properties = _runtime_capability_properties()
    assert properties == {"playwright", "takumi", "available_names"}
    current_text = "\n".join(path.read_text("utf-8") for path in _documentation_files())
    missing = sorted(
        name
        for name in ("playwright", "takumi")
        if re.search(rf"\bcapabilities\.{name}\b", current_text) is None
    )
    assert not missing, "First-party capabilities are undocumented: " + ", ".join(
        missing
    )
    assert "service.graphics" in current_text


def test_backend_runtime_dependency_boundaries_are_documented() -> None:
    playwright_text = (
        ROOT / "docs" / "configuration" / "providers" / "playwright.md"
    ).read_text("utf-8")
    skia_text = (ROOT / "docs" / "configuration" / "graphics" / "skia.md").read_text(
        "utf-8"
    )
    provider_matrix = (ROOT / "docs" / "start" / "choosing-provider.md").read_text(
        "utf-8"
    )

    assert "uv run playwright install --with-deps chromium" in playwright_text
    assert "PLAYWRIGHT_BROWSERS_PATH" in playwright_text
    for dependency in ("libEGL.so.1", "libGL.so.1", "libexpat.so.1"):
        assert f"`{dependency}`" in skia_text
    assert 'uv run python3 -c "import skia"' in skia_text
    for implementation in ("Playwright", "Takumi", "Pillow", "Skia"):
        assert re.search(
            rf"^\| {implementation} \|",
            provider_matrix,
            flags=re.MULTILINE,
        )


def test_cache_and_scoped_resource_boundaries_are_documented() -> None:
    cache_guide = (ROOT / "docs" / "guides" / "cache-lifecycle.md").read_text("utf-8")
    navigation = (ROOT / "mkdocs.yml").read_text("utf-8")
    resource_reference = (ROOT / "docs" / "configuration" / "resources.md").read_text(
        "utf-8"
    )

    assert "guides/cache-lifecycle.md" in navigation
    for cache_name in (
        "`resource`",
        "`template_environment`",
        "`filehost`",
        "`takumi_compiled`",
    ):
        assert cache_name in cache_guide
    assert "refresh=True" in resource_reference
    assert "ResourceAccess.publish" in resource_reference
    assert "PublishedResource" in resource_reference


def test_documented_top_level_imports_exist() -> None:
    exports = _top_level_exports()
    parsed, _ = _parse_python_sources()
    missing: list[str] = []
    for source, tree in parsed:
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module != PACKAGE:
                continue
            for alias in node.names:
                if alias.name not in exports:
                    lineno = source.lineno + node.lineno - 1
                    missing.append(f"{source.path}:{lineno}: {alias.name}")
    assert not missing, (
        f"Examples import names absent from {PACKAGE}.__all__:\n  "
        + "\n  ".join(missing)
    )


def test_extension_docs_cover_the_final_architecture_vocabulary() -> None:
    architecture_text = "\n".join(
        path.read_text("utf-8")
        for path in sorted(DOCUMENTATION_ROOTS["architecture"].rglob("*.md"))
    )
    missing = sorted(
        term
        for term in EXPECTED_ARCHITECTURE_TERMS
        if re.search(rf"\b{re.escape(term)}\b", architecture_text) is None
    )
    assert not missing, "Maintainer docs omit concepts: " + ", ".join(missing)


def _annotation_name(annotation: ast.expr) -> str | None:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    return None


def _is_class_variable(annotation: ast.expr) -> bool:
    return (
        isinstance(annotation, ast.Subscript)
        and _annotation_name(annotation.value) == "ClassVar"
    )


def _config_model_fields() -> dict[str, dict[str, str | None]]:
    tree = ast.parse(SETTINGS_PATH.read_text("utf-8"), filename=str(SETTINGS_PATH))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}

    def inherits_base_model(name: str, seen: frozenset[str] = frozenset()) -> bool:
        if name in seen or name not in classes:
            return False
        bases = {
            base_name
            for base in classes[name].bases
            if (base_name := _annotation_name(base)) is not None
        }
        return "BaseModel" in bases or any(
            inherits_base_model(base, seen | {name}) for base in bases
        )

    models: dict[str, dict[str, str | None]] = {}
    for name, node in classes.items():
        if not inherits_base_model(name):
            continue
        fields: dict[str, str | None] = {}
        for statement in node.body:
            if (
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and not _is_class_variable(statement.annotation)
            ):
                fields[statement.target.id] = _annotation_name(statement.annotation)
        models[name] = fields
    return models


def _config_leaf_paths() -> frozenset[str]:
    models = _config_model_fields()
    leaves: set[str] = set()

    def visit(model: str, prefix: tuple[str, ...]) -> None:
        for field_name, annotation in models[model].items():
            path = (*prefix, field_name)
            if annotation in models:
                visit(annotation, path)
            else:
                leaves.add(".".join(path))

    assert "HtmlRenderConfig" in models
    visit("HtmlRenderConfig", ())
    return frozenset(leaves)


def test_config_schema_and_documentation_stay_in_sync() -> None:
    schema_paths = _config_leaf_paths()
    assert schema_paths == EXPECTED_CONFIG_PATHS
    config_text = "\n".join(
        path.read_text("utf-8")
        for path in sorted(DOCUMENTATION_ROOTS["configuration"].rglob("*.md"))
    )
    missing_docs = sorted(path for path in schema_paths if path not in config_text)
    assert not missing_docs, "Configuration fields are undocumented: " + ", ".join(
        missing_docs
    )
