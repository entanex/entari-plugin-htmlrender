"""Static contracts for the typed provider and host-neutral runtime graph."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "entari_plugin_htmlrender"
SDK_PATH = PACKAGE_ROOT / "providers" / "sdk.py"
RUNTIME_PATH = PACKAGE_ROOT / "runtime" / "runtime.py"

EXPECTED_PROVIDER_DEPENDENCIES = frozenset(
    {
        "asset_publisher",
        "cache_observer",
        "operation_admission",
        "operation_observer",
        "resources",
    }
)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text("utf-8"), filename=str(path))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} must be defined in the contracted module")


def _method(class_node: ast.ClassDef, name: str) -> ast.FunctionDef:
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{class_node.name}.{name} must be defined")


def _field_names(class_node: ast.ClassDef) -> frozenset[str]:
    return frozenset(
        node.target.id
        for node in class_node.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    )


def _annotation_name(annotation: ast.expr | None) -> str | None:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    return None


def _argument_annotation(method: ast.FunctionDef, name: str) -> str | None:
    arguments = (*method.args.posonlyargs, *method.args.args, *method.args.kwonlyargs)
    for argument in arguments:
        if argument.arg == name:
            return _annotation_name(argument.annotation)
    raise AssertionError(f"{method.name} must accept {name}")


def _is_protocol_of_config(base: ast.expr) -> bool:
    return (
        isinstance(base, ast.Subscript)
        and _annotation_name(base.value) == "Protocol"
        and _annotation_name(base.slice) == "ConfigT"
    )


def test_render_provider_is_generic_over_one_typed_config_flow() -> None:
    tree = _tree(SDK_PATH)
    provider = _class(tree, "RenderProvider")
    assert any(_is_protocol_of_config(base) for base in provider.bases), (
        "RenderProvider must be declared as Protocol[ConfigT]"
    )

    typed_config_methods = (
        "check_availability",
        "compose",
        "resource_strategy",
    )
    for name in typed_config_methods:
        method = _method(provider, name)
        assert _argument_annotation(method, "config") == "ConfigT", (
            f"RenderProvider.{name} must consume ConfigT"
        )

    parse_config = _method(provider, "parse_config")
    assert _annotation_name(parse_config.returns) == "ConfigT"
    resource_strategy = _method(provider, "resource_strategy")
    assert _annotation_name(resource_strategy.returns) == "ResourceStrategy"

    method_names = {
        node.name for node in provider.body if isinstance(node, ast.FunctionDef)
    }
    assert method_names == {
        "id",
        "parse_config",
        "check_availability",
        "resource_strategy",
        "compose",
    }


def test_provider_dtos_carry_the_final_resource_dependencies_and_strategy() -> None:
    tree = _tree(SDK_PATH)
    dependencies = _field_names(_class(tree, "ProviderDependencies"))
    bindings = _field_names(_class(tree, "ProviderBinding"))

    assert dependencies == EXPECTED_PROVIDER_DEPENDENCIES, (
        "ProviderDependencies must expose only the provider-facing resource boundary"
    )
    assert "resource_strategy" not in bindings, (
        "ResourceStrategy must have one source of truth: "
        "RenderProvider.resource_strategy(), evaluated before composition"
    )
    assert {"description", "observation_attributes"}.isdisjoint(bindings), (
        "ProviderBinding must not advertise metadata fields with no runtime contract"
    )


def test_runtime_exposes_dedicated_service_facades_from_composition() -> None:
    runtime = _class(_tree(RUNTIME_PATH), "RenderRuntime")
    initializer = _method(runtime, "__init__")
    parameters = {
        argument.arg
        for argument in (*initializer.args.args, *initializer.args.kwonlyargs)
    }
    expected_services = {
        "renderer",
        "templates",
        "resources",
        "graphics",
        "capabilities",
    }
    assert expected_services <= parameters

    properties = {
        node.name
        for node in runtime.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Name) and decorator.id == "property"
            for decorator in node.decorator_list
        )
    }
    assert expected_services <= properties
