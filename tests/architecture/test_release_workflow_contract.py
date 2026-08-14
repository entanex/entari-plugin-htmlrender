"""Contracts shared by release and distribution verification workflows."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
LOCAL_ACTIONS = ROOT / ".github" / "actions"
RULESETS = ROOT / ".github" / "rulesets"
MAKEFILE = ROOT / "Makefile"
BUILD_DISTRIBUTIONS = "uses: ./.github/actions/build-distributions"
BUILD_DOCS = "uses: ./.github/actions/build-docs"
SETUP_PROJECT = "uses: ./.github/actions/setup-project"
SKIA_SETUP = "uses: ./.github/actions/setup-skia-runtime"
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_USES = re.compile(r"^\s*uses:\s+([^\s@]+)@([^\s#]+)", re.MULTILINE)


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_skia_runtime_action_owns_linux_dependencies() -> None:
    action = (LOCAL_ACTIONS / "setup-skia-runtime" / "action.yml").read_text(
        encoding="utf-8"
    )

    assert "using: composite" in action
    for package in ("libegl1", "libexpat1", "libgl1"):
        assert package in action

    for workflow in WORKFLOWS.glob("*.yml"):
        assert "sudo apt-get install" not in workflow.read_text(encoding="utf-8")


def test_all_skia_smoke_workflows_use_shared_runtime_setup() -> None:
    expected_uses = {
        "auto-tag.yml": 1,
        "ci.yml": 2,
        "coverage.yml": 1,
        "publish-test.yml": 1,
        "publish.yml": 1,
    }

    for workflow, count in expected_uses.items():
        assert _workflow(workflow).count(SKIA_SETUP) == count


def test_distribution_preflight_installs_skia_runtime_first() -> None:
    for workflow in ("auto-tag.yml", "ci.yml", "publish-test.yml", "publish.yml"):
        content = _workflow(workflow)
        assert BUILD_DISTRIBUTIONS in content
        assert content.index(SKIA_SETUP) < content.index(BUILD_DISTRIBUTIONS)


def test_distribution_action_owns_the_build_and_verification_pipeline() -> None:
    action = (LOCAL_ACTIONS / "build-distributions" / "action.yml").read_text(
        encoding="utf-8"
    )

    for command in (
        "uv build --clear --no-sources --wheel --sdist",
        "twine check dist/*",
        "make verify-artifacts DIST_DIR=dist",
        "sha256sum dist/*",
    ):
        assert command in action

    expected_uses = {
        "auto-tag.yml": 1,
        "ci.yml": 1,
        "publish-test.yml": 1,
        "publish.yml": 1,
    }
    for workflow, count in expected_uses.items():
        assert _workflow(workflow).count(BUILD_DISTRIBUTIONS) == count

    for workflow in WORKFLOWS.glob("*.yml"):
        content = workflow.read_text(encoding="utf-8")
        assert "uv build " not in content
        assert "make verify-artifacts" not in content


def test_project_and_docs_setup_have_single_owners() -> None:
    setup = (LOCAL_ACTIONS / "setup-project" / "action.yml").read_text(encoding="utf-8")
    docs = (LOCAL_ACTIONS / "build-docs" / "action.yml").read_text(encoding="utf-8")

    assert "astral-sh/setup-uv@" in setup
    for scope in ("all)", "docs)", "test)"):
        assert scope in setup
    assert "uv run zensical build --strict" in docs

    for workflow in WORKFLOWS.glob("*.yml"):
        content = workflow.read_text(encoding="utf-8")
        assert "astral-sh/setup-uv@" not in content
        assert "uv sync " not in content
        assert "uv run zensical build --strict" not in content

    assert _workflow("docs.yml").count(BUILD_DOCS) == 1
    assert _workflow("docs-pr-preview.yml").count(BUILD_DOCS) == 1
    assert _workflow("publish.yml").count(BUILD_DOCS) == 1
    assert SETUP_PROJECT in _workflow("coverage.yml")


def test_production_workflows_use_the_entari_loader_smoke() -> None:
    for workflow in WORKFLOWS.glob("*.yml"):
        assert "tests/host" not in workflow.read_text(encoding="utf-8")

    ci = _workflow("ci.yml")
    assert "uv run pytest tests/entari/test_plugin.py -q --no-cov" in ci


def test_external_actions_are_pinned_to_full_commit_shas() -> None:
    action_files = [*WORKFLOWS.glob("*.yml"), *LOCAL_ACTIONS.glob("*/action.yml")]

    for action_file in action_files:
        for action, revision in _USES.findall(action_file.read_text(encoding="utf-8")):
            assert _FULL_SHA.fullmatch(revision), (
                f"{action_file.relative_to(ROOT)}: {action}@{revision} is not SHA-pinned"
            )


def test_required_check_contexts_remain_stable() -> None:
    ruleset = (RULESETS / "protect-main.json").read_text(encoding="utf-8")

    assert "name: Required Checks" in _workflow("ci.yml")
    assert "name: Coverage Matrix" in _workflow("coverage.yml")
    assert "name: Prek" in _workflow("prek.yml")
    assert "name: Docs Preview" in _workflow("docs-pr-preview.yml")
    for context in ("Required Checks", "Coverage Matrix", "Prek", "Docs Preview"):
        assert f'"context": "{context}"' in ruleset


def test_local_and_remote_coverage_gates_share_the_release_threshold() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    coverage = _workflow("coverage.yml")

    assert "COVERAGE_FAIL_UNDER ?= 90" in makefile
    assert "--cov-fail-under=$(COVERAGE_FAIL_UNDER)" in makefile
    assert "--cov-fail-under=90" in coverage


def test_pre_tag_recovery_preserves_release_gates() -> None:
    workflow = _workflow("auto-tag.yml")
    docs_trigger = _workflow("docs.yml").partition("permissions:")[0]

    assert "workflow_dispatch:" in workflow
    assert "source_sha:" in workflow
    assert '"${SOURCE_SHA}" != "${MASTER_SHA}"' in workflow
    assert "Tag ${TAG} already exists; recover with Publish instead." in workflow
    assert "paths:" not in docs_trigger
    for required in (
        "CI:ci.yml",
        "Coverage:coverage.yml",
        "Docs:docs.yml",
        "Prek:prek.yml",
    ):
        assert required in workflow
