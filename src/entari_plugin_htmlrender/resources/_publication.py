"""Internal validation shared by publication boundaries."""

from __future__ import annotations

import re

from entari_plugin_htmlrender.errors import InvalidRenderInputError

_PUBLICATION_SUFFIX_RE = re.compile(r"\.?[A-Za-z0-9][A-Za-z0-9._-]{0,31}\Z")


def normalize_publication_suffix(value: str | None) -> str | None:
    """Return one canonical extension segment or reject the caller input."""

    if value is None:
        return None
    if not isinstance(value, str) or _PUBLICATION_SUFFIX_RE.fullmatch(value) is None:
        raise InvalidRenderInputError(
            "Publication suffix must be one extension segment containing "
            "1-32 ASCII letters, digits, dots, underscores, or hyphens.",
            operation="publish",
            field="suffix",
        )
    extension = value.removeprefix(".")
    return f".{extension.lower()}"


__all__ = ["normalize_publication_suffix"]
