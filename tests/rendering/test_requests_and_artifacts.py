from __future__ import annotations

from dataclasses import replace
from typing import cast, get_type_hints
import zlib

import pytest

from entari_plugin_htmlrender.preparation import PreparedHtml, RasterOptions
from entari_plugin_htmlrender.raster import RasterImageFormat
from entari_plugin_htmlrender.rendering import PreparedHtmlExecutor, RenderOperation
from entari_plugin_htmlrender.rendering.artifacts import RenderedHtml, RenderedImage
from entari_plugin_htmlrender.resources.config import (
    ResourceMaterializationPolicy,
)
from tests.image_fixtures import encoded_image


def _png_ihdr(
    *,
    width: int = 1,
    height: int = 1,
    bit_depth: int = 8,
    color_type: int = 6,
    compression: int = 0,
    filter_method: int = 0,
    interlace: int = 0,
) -> bytes:
    payload = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes(
            (bit_depth, color_type, compression, filter_method, interlace),
        )
    )
    chunk_type = b"IHDR"
    return (
        b"\x89PNG\r\n\x1a\n"
        + len(payload).to_bytes(4, "big")
        + chunk_type
        + payload
        + zlib.crc32(chunk_type + payload).to_bytes(4, "big")
    )


def _jpeg_segment(marker: int, payload: bytes, *, length: int | None = None) -> bytes:
    segment_length = len(payload) + 2 if length is None else length
    return (
        b"\xff\xd8\xff" + bytes((marker,)) + segment_length.to_bytes(2, "big") + payload
    )


def test_rendered_image_exposes_bytes_and_media_type() -> None:
    data = encoded_image("png", width=800, height=600)
    image = RenderedImage.from_bytes(data, expected_format="png")

    assert bytes(image) == data
    assert image.media_type == "image/png"
    assert image.format == "png"
    assert image.width == 800
    assert image.height == 600


def test_public_raster_annotations_resolve_at_runtime() -> None:
    assert get_type_hints(RasterOptions)["format"] == RasterImageFormat
    assert get_type_hints(RenderedImage)["format"] == RasterImageFormat


def test_public_executor_annotations_resolve_at_runtime() -> None:
    annotations = get_type_hints(PreparedHtmlExecutor.execute)

    assert annotations == {
        "prepared": PreparedHtml,
        "options": RasterOptions,
        "operation": RenderOperation,
        "materialization_policy": ResourceMaterializationPolicy | None,
        "return": RenderedImage,
    }


def test_dataclass_replace_reinspects_encoded_metadata() -> None:
    original = RenderedImage.from_bytes(encoded_image("png", width=11, height=7))
    replacement_data = encoded_image("jpeg", width=19, height=13)

    replacement = replace(original, data=replacement_data)

    assert replace(original) == original
    assert replacement.data == replacement_data
    assert replacement.format == "jpeg"
    assert (replacement.width, replacement.height) == (19, 13)


def test_rendered_image_parses_jpeg_metadata() -> None:
    data = encoded_image("jpeg", width=37, height=29)

    image = RenderedImage.from_bytes(data)

    assert image.format == "jpeg"
    assert image.media_type == "image/jpeg"
    assert image.width == 37
    assert image.height == 29


def test_rendered_image_parses_progressive_jpeg_scans() -> None:
    data = encoded_image("jpeg", width=43, height=31, progressive=True)
    assert data.count(b"\xff\xda") > 1

    image = RenderedImage.from_bytes(data, expected_format="jpeg")

    assert (image.width, image.height) == (43, 31)


def test_rendered_image_accepts_jpeg_standalone_marker() -> None:
    data = encoded_image("jpeg", width=17, height=13)
    with_tem_marker = data[:2] + b"\xff\x01" + data[2:]

    image = RenderedImage.from_bytes(with_tem_marker)

    assert image.format == "jpeg"
    assert (image.width, image.height) == (17, 13)


@pytest.mark.parametrize(
    ("encoded_format", "expected_format"),
    [("png", "jpeg"), ("jpeg", "png")],
)
def test_rendered_image_rejects_format_mismatch(
    encoded_format: RasterImageFormat,
    expected_format: RasterImageFormat,
) -> None:
    with pytest.raises(ValueError, match="format mismatch"):
        RenderedImage.from_bytes(
            encoded_image(encoded_format),
            expected_format=expected_format,
        )


def test_rendered_image_rejects_corrupt_png_metadata() -> None:
    corrupted = bytearray(encoded_image("png"))
    corrupted[19] ^= 0x01

    with pytest.raises(ValueError, match="checksum"):
        RenderedImage.from_bytes(bytes(corrupted))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"\x89PNG\r\n\x1a\n", "IHDR chunk is truncated"),
        (
            b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0cIDAT" + b"\x00" * 17,
            "IHDR must be the first",
        ),
        (_png_ihdr(width=0), "dimensions must be positive"),
        (_png_ihdr(color_type=5), "unsupported color type or bit depth"),
        (_png_ihdr(compression=1), "unsupported encoding methods"),
    ],
)
def test_rendered_image_rejects_invalid_png_container(
    data: bytes,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        RenderedImage.from_bytes(data)


def test_rendered_image_rejects_truncated_jpeg_metadata() -> None:
    with pytest.raises(ValueError, match="JPEG"):
        RenderedImage.from_bytes(b"\xff\xd8\xff\xc0\x00")


def test_rendered_image_rejects_jpeg_scan_before_frame() -> None:
    scan_without_frame = b"\xff\xd8\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\xff\xd9"

    with pytest.raises(ValueError, match="scan appears before frame"):
        RenderedImage.from_bytes(scan_without_frame)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"\xff\xd8", "marker stream is truncated"),
        (b"\xff\xd8\x01\x00", "expected a marker prefix"),
        (b"\xff\xd8\xff\x00", "unexpected stuffed marker byte"),
        (b"\xff\xd8\xff\xd9", "image ends before frame dimensions"),
        (b"\xff\xd8\xff\xd8", "unexpected marker"),
        (b"\xff\xd8\xff\xe0\x00", "segment length is truncated"),
        (b"\xff\xd8\xff\xe0\x00\x01", "invalid segment length"),
        (b"\xff\xd8\xff\xe0\x00\x04\x00", "segment payload is truncated"),
        (_jpeg_segment(0xC0, b"\x00" * 8, length=10), "frame segment is truncated"),
        (
            _jpeg_segment(
                0xC0,
                b"\x08\x00\x01\x00\x01\x02\x01\x11\x00",
            ),
            "frame components are inconsistent",
        ),
        (
            _jpeg_segment(
                0xC0,
                b"\x08\x00\x00\x00\x01\x01\x01\x11\x00",
            ),
            "frame dimensions must be positive",
        ),
        (_jpeg_segment(0xE0, b""), "no frame dimensions were found"),
        (b"\xff\xd8\xff\xff", "no frame dimensions were found"),
    ],
)
def test_rendered_image_rejects_invalid_jpeg_container(
    data: bytes,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        RenderedImage.from_bytes(data)


def test_rendered_image_rejects_unknown_signature_and_mutable_data() -> None:
    with pytest.raises(ValueError, match="PNG or JPEG signature"):
        RenderedImage.from_bytes(b"not-an-image")
    with pytest.raises(TypeError, match="data must be bytes"):
        RenderedImage(cast("bytes", bytearray(encoded_image("png"))))


def test_rendered_html_stringifies_to_content() -> None:
    artifact = RenderedHtml(content="<p>hi</p>")

    assert str(artifact) == "<p>hi</p>"
    assert artifact.content == "<p>hi</p>"


@pytest.mark.parametrize("content", [None, 123, b"<p>hi</p>"])
def test_rendered_html_rejects_non_string_content(content: object) -> None:
    with pytest.raises(TypeError, match="content must be a string"):
        RenderedHtml(content=cast("str", content))


def test_render_operation_identity_is_output_explicit() -> None:
    assert {operation.value for operation in RenderOperation} == {
        "html_to_image",
        "text_to_image",
        "markdown_to_image",
        "template_to_image",
        "prepared_html_to_image",
        "raster_scene_to_image",
        "template_to_html",
    }
    assert all("rasterize" not in operation.value for operation in RenderOperation)
