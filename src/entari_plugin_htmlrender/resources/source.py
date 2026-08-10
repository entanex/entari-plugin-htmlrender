"""Logical package and filesystem resource sources.

Package resources are addressed by stable logical names and never exposed as
filesystem paths.  Filesystem resources retain their concrete path so callers
can opt into revalidation where appropriate.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath

from .models import FileResourceRef, PackageResourceRef


def _logical_parts(name: str | PurePosixPath) -> tuple[str, ...]:
    logical = PurePosixPath(str(name))
    parts = logical.parts
    if (
        not parts
        or logical.is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"Invalid logical resource name: {name!r}")
    return parts


@dataclass(frozen=True, slots=True)
class PackageResourceSource:
    package: str
    root: str = ""

    def __post_init__(self) -> None:
        if self.root:
            object.__setattr__(
                self,
                "root",
                PurePosixPath(*_logical_parts(self.root)).as_posix(),
            )

    @property
    def identity(self) -> tuple[str, str, str]:
        return ("package", self.package, self.root)

    def resource(self, name: str | PurePosixPath) -> PackageResourceRef:
        parts = _logical_parts(name)
        logical = (
            PurePosixPath(self.root, *parts) if self.root else PurePosixPath(*parts)
        )
        return PackageResourceRef(self.package, logical.as_posix())


@dataclass(frozen=True, slots=True)
class FilesystemResourceSource:
    root: Path

    def __post_init__(self) -> None:
        root = Path(os.path.normpath(self.root))
        if not root.is_absolute():
            raise ValueError("Filesystem resource sources require an absolute root.")
        object.__setattr__(self, "root", root)

    @property
    def identity(self) -> tuple[str, str]:
        return ("filesystem", str(self.root))

    def resource(self, name: str | PurePosixPath) -> FileResourceRef:
        parts = _logical_parts(name)
        candidate = Path(os.path.normpath(self.root.joinpath(*parts)))
        try:
            candidate.relative_to(self.root)
        except ValueError as error:
            raise ValueError(f"Resource escapes filesystem root: {name!r}") from error
        return FileResourceRef(candidate)


__all__ = [
    "FilesystemResourceSource",
    "PackageResourceSource",
]
