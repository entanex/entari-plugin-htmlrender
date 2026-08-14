"""Regression tests for release archive boundaries."""

from pathlib import Path

import pytest

from scripts.verify_distribution import (
    _BASE_SMOKE,
    _ENTARI_PLUGIN_SMOKE,
    _GRAPHICS_SMOKE,
    _TAKUMI_SMOKE,
    DistributionVerificationError,
    _validate_archive_paths,
)

_INSTALL_SMOKES = {
    "core": _BASE_SMOKE,
    "entari": _ENTARI_PLUGIN_SMOKE,
    "takumi": _TAKUMI_SMOKE,
    "graphics": _GRAPHICS_SMOKE,
}


@pytest.mark.parametrize(
    "member",
    [
        "project-0.1.0/.git/objects/pack",
        "project-0.1.0/.GIT/config",
        "project-0.1.0/.jj/repo/store/type",
        "project-0.1.0/.cache/tool/state",
        "project-0.1.0/build/lib/package.py",
        "project-0.1.0/docs/.DS_Store",
        "package/__pycache__/module.cpython-312.pyc",
        "package-0.1.0.egg-info/PKG-INFO",
    ],
)
def test_distribution_archive_guard_rejects_repository_artifacts(
    member: str,
) -> None:
    with pytest.raises(DistributionVerificationError, match="forbidden VCS"):
        _validate_archive_paths([member], artifact=Path("artifact.tar.gz"))


def test_distribution_archive_guard_allows_release_metadata() -> None:
    _validate_archive_paths(
        [
            "project-0.1.0/PKG-INFO",
            "project-0.1.0/src/package/__init__.py",
            "package-0.1.0.dist-info/METADATA",
            "package-0.1.0.dist-info/RECORD",
        ],
        artifact=Path("artifact.tar.gz"),
    )


@pytest.mark.parametrize(("name", "source"), _INSTALL_SMOKES.items())
def test_distribution_install_smokes_are_valid_python(
    name: str,
    source: str,
) -> None:
    compile(source, f"<{name}-distribution-smoke>", "exec")


def test_distribution_install_smokes_use_the_semantic_runtime_surface() -> None:
    assert "HtmlRenderConfig" in _BASE_SMOKE
    assert "build_runtime_plan" in _BASE_SMOKE
    assert "runtime.templates.render" in _BASE_SMOKE
    assert "runtime.resources.fetch_text" in _BASE_SMOKE
    assert "runtime.renderer.supported_operations" in _BASE_SMOKE
    assert "runtime.capabilities.available_names" in _BASE_SMOKE

    assert "runtime.capabilities.takumi" in _TAKUMI_SMOKE
    assert "capability.lease_session()" in _TAKUMI_SMOKE
    assert "runtime.renderer.rasterize_text" in _TAKUMI_SMOKE

    assert "GraphicsSettings" in _GRAPHICS_SMOKE
    assert 'for backend in ("pillow", "skia")' in _GRAPHICS_SMOKE
    assert "runtime.graphics.rasterize" in _GRAPHICS_SMOKE
    assert "runtime.graphics.render" not in _GRAPHICS_SMOKE


@pytest.mark.parametrize(
    "removed_surface",
    [
        "entari_plugin_htmlrender.host",
        "compose_runtime",
        "RenderSettings",
        "runtime.extensions",
        "capability.api()",
        "RenderRasterSceneRequest",
        "PILLOW_RASTER_SCENE_RENDERER",
        "SKIA_RASTER_SCENE_RENDERER",
        "from entari_plugin_htmlrender import render_text",
    ],
)
def test_distribution_install_smokes_do_not_retain_removed_surfaces(
    removed_surface: str,
) -> None:
    combined = "\n".join(_INSTALL_SMOKES.values())
    assert removed_surface not in combined
