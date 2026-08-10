"""Request-header capability merging shared by hosted-asset consumers.

Both the hosted asset route (validating inbound requests) and the Playwright
request route (injecting authorization on outbound fetches) must use the
same merge semantics: identical values deduplicate, conflicting capability
values fail loudly, and a formal capability always overrides a caller-preset
value for the same header — a preset wrong value must never win via
``setdefault``-style merging.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class RequestHeaderConflict(ValueError):
    """Two capabilities declare different values for the same header."""


_HTTP_TOKEN_PATTERN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")


def validate_request_header_name(value: str) -> str:
    """Require an RFC 9110 token before a value reaches an HTTP adapter."""
    if _HTTP_TOKEN_PATTERN.fullmatch(value) is None:
        raise ValueError("request header name must be a valid HTTP token")
    return value


def validate_request_header_value(value: str) -> str:
    """Reject control characters that could create or split HTTP fields."""
    if any(ord(character) < 0x20 and character != "\t" for character in value):
        raise ValueError("request header value must not contain control characters")
    if any(ord(character) == 0x7F for character in value):
        raise ValueError("request header value must not contain control characters")
    return value


def merge_request_headers(
    preset: Mapping[str, str],
    capability: Mapping[str, str],
) -> dict[str, str]:
    """Overlay capability headers onto caller-preset headers.

    Header names compare case-insensitively; the capability's value and
    spelling replace any preset entry for the same header.
    """
    authoritative = {name.lower() for name in capability}
    merged = {
        name: value
        for name, value in preset.items()
        if name.lower() not in authoritative
    }
    merged.update(capability)
    return merged


def combine_request_capabilities(
    existing: Mapping[str, str],
    incoming: Mapping[str, str],
) -> dict[str, str]:
    """Combine two capability maps; identical values deduplicate, else fail."""
    combined = dict(existing)
    lowered = {name.lower(): name for name in existing}
    for name, value in incoming.items():
        held = lowered.get(name.lower())
        if held is None:
            combined[name] = value
            lowered[name.lower()] = name
            continue
        if combined[held] != value:
            raise RequestHeaderConflict(
                f"Conflicting request capability values for header {name!r}."
            )
    return combined


__all__ = [
    "RequestHeaderConflict",
    "combine_request_capabilities",
    "merge_request_headers",
    "validate_request_header_name",
    "validate_request_header_value",
]
