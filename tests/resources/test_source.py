from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from entari_plugin_htmlrender.errors import InvalidRenderInputError
from entari_plugin_htmlrender.resources.models import (
    FileResourceRef,
    InlineResource,
    PackageResourceRef,
    PublishedResource,
    RemoteResourceRef,
    ResourceContent,
    ResourceRevision,
)
from entari_plugin_htmlrender.resources.source import (
    FilesystemResourceSource,
    PackageResourceSource,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def test_resource_models_have_stable_structural_identities(tmp_path: Path) -> None:
    path = tmp_path / "folder" / ".." / "asset.css"
    file_reference = FileResourceRef(path)
    package_reference = PackageResourceRef("example_package", "assets/card.css")
    remote_reference = RemoteResourceRef("https://assets.example/card.css?v=1")
    inline_resource = InlineResource(b"card", "text/css")

    lexical_path = (tmp_path / "asset.css").absolute()
    assert file_reference.path == lexical_path
    assert file_reference.identity == ("file", str(lexical_path))
    assert package_reference.identity == (
        "package",
        "example_package",
        "assets/card.css",
    )
    assert remote_reference.identity == (
        "remote",
        "https://assets.example/card.css?v=1",
    )
    assert inline_resource.identity == (
        "inline",
        sha256(b"card").digest(),
        4,
        "text/css",
    )
    assert ResourceContent(
        b"card",
        "text/css",
        ResourceRevision("revision"),
    ).revision == ResourceRevision("revision")


def test_inline_resource_rejects_mutable_payloads() -> None:
    with pytest.raises(InvalidRenderInputError, match="immutable bytes") as captured:
        InlineResource(cast("bytes", bytearray(b"mutable")))
    assert captured.value.operation == "create_inline_resource"
    assert captured.value.field == "data"


def test_file_reference_freezes_absolute_lexical_identity() -> None:
    traversing = FileResourceRef(Path("assets") / ".." / "logo.png")
    direct = FileResourceRef(Path("logo.png"))

    assert traversing.path == direct.path
    assert traversing == direct
    assert hash(traversing) == hash(direct)
    assert traversing.identity == direct.identity


def test_remote_reference_normalizes_fetch_identity() -> None:
    decorated = RemoteResourceRef("HTTPS://EXAMPLE.COM:443/a#section")
    direct = RemoteResourceRef("https://example.com/a")

    assert decorated == direct
    assert decorated.url == "https://example.com/a"
    assert decorated.identity == direct.identity


@pytest.mark.parametrize(
    "url",
    [
        "https://user@example.com/private",
        "https://user:secret@example.com/private",
        "https://example.com:0/asset",
        "https://example.com:/asset",
        "https://example.com:99999/asset",
    ],
)
def test_remote_reference_rejects_ambiguous_or_sensitive_authority(
    url: str,
) -> None:
    with pytest.raises(InvalidRenderInputError) as raised:
        RemoteResourceRef(url)

    assert raised.value.operation == "create_remote_resource_ref"
    assert raised.value.field == "url"


@pytest.mark.parametrize(
    ("factory", "operation", "field"),
    [
        (
            lambda: FileResourceRef(cast("Path", object())),
            "create_file_resource_ref",
            "path",
        ),
        (
            lambda: PackageResourceRef("", "asset.css"),
            "create_package_resource_ref",
            "package",
        ),
        (
            lambda: RemoteResourceRef(cast("str", object())),
            "create_remote_resource_ref",
            "url",
        ),
        (
            lambda: ResourceContent(b"value", media_type=""),
            "create_resource_content",
            "media_type",
        ),
        (
            lambda: InlineResource(b"value", media_type=""),
            "create_inline_resource",
            "media_type",
        ),
        (
            lambda: ResourceRevision(""),
            "create_resource_revision",
            "token",
        ),
    ],
)
def test_resource_value_validation_uses_structured_invalid_input(
    factory: object,
    operation: str,
    field: str,
) -> None:
    callable_factory = cast("Callable[[], object]", factory)
    with pytest.raises(InvalidRenderInputError) as captured:
        callable_factory()

    assert captured.value.operation == operation
    assert captured.value.field == field


@pytest.mark.parametrize(
    "headers",
    [
        {"Bad Header": "value"},
        {"X-Test": "value\r\nInjected: true"},
        {"X-Test": "value\x7f"},
        {"X-Test": "one", "x-test": "two"},
    ],
)
def test_published_resource_rejects_invalid_http_headers(
    headers: dict[str, str],
) -> None:
    with pytest.raises(InvalidRenderInputError) as captured:
        PublishedResource(
            "https://assets.example/resource",
            request_headers=headers,
        )

    assert captured.value.operation == "create_published_resource"
    assert captured.value.field == "request_headers"


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "/absolute.css", "assets/../secret.css", "assets\\card.css"],
)
def test_package_reference_rejects_non_logical_names(name: str) -> None:
    with pytest.raises(InvalidRenderInputError, match="Invalid logical resource name"):
        PackageResourceRef("example_package", name)


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "data:text/plain,secret", "relative/file.css", "https:"],
)
def test_remote_reference_rejects_non_http_urls(url: str) -> None:
    with pytest.raises(InvalidRenderInputError, match="http:// or https://"):
        RemoteResourceRef(url)


def test_package_source_builds_logical_references() -> None:
    source = PackageResourceSource("example_package", "assets/styles")

    assert source.identity == ("package", "example_package", "assets/styles")
    assert source.resource("themes/light.css") == PackageResourceRef(
        "example_package",
        "assets/styles/themes/light.css",
    )
    with pytest.raises(ValueError, match="Invalid logical resource name"):
        source.resource("../secret.css")


def test_filesystem_source_canonicalizes_and_contains_resources(tmp_path: Path) -> None:
    root = tmp_path / "templates"
    root.mkdir()
    source = FilesystemResourceSource(root / ".")

    assert source.root == root.resolve()
    assert source.identity == ("filesystem", str(root.resolve()))
    assert source.resource("nested/card.html") == FileResourceRef(
        root / "nested" / "card.html"
    )
    with pytest.raises(ValueError, match="Invalid logical resource name"):
        source.resource("../outside.html")


def test_filesystem_source_does_not_traverse_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    source = FilesystemResourceSource(root)

    reference = source.resource("linked/secret.txt")

    assert reference.path == root / "linked" / "secret.txt"
