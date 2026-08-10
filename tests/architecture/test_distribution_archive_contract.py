"""Regression tests for release archive boundaries."""

from pathlib import Path

import pytest

from scripts.verify_distribution import (
    DistributionVerificationError,
    _validate_archive_paths,
)


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
