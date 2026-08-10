from __future__ import annotations

import pytest

from entari_plugin_htmlrender.preparation.media import (
    guess_asset_media_type,
    sniff_media_type,
)
from entari_plugin_htmlrender.preparation.models import PreparedAsset


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"\x89PNG\r\n\x1a\nrest", "image/png"),
        (b"\xff\xd8\xffrest", "image/jpeg"),
        (b"GIF87arest", "image/gif"),
        (b"GIF89arest", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBPrest", "image/webp"),
        (b"wOF2rest", "font/woff2"),
        (b"wOFFrest", "font/woff"),
        (b"  \n<svg xmlns='http://www.w3.org/2000/svg'>", "image/svg+xml"),
        (b"unrecognized", "application/octet-stream"),
    ],
)
def test_sniff_media_type_classifies_supported_magic_bytes(
    payload: bytes,
    expected: str,
) -> None:
    assert sniff_media_type(payload) == expected


def test_guess_asset_media_type_prefers_declaration_then_filename() -> None:
    declared = PreparedAsset("icon.unknown", b"data", "image/custom")
    inferred = PreparedAsset("styles/card.css", b"data")
    unknown = PreparedAsset("memory:asset", b"data")

    assert guess_asset_media_type(declared) == "image/custom"
    assert guess_asset_media_type(inferred) == "text/css"
    assert guess_asset_media_type(unknown) is None
