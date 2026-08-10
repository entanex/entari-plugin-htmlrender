from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import NewType, TypeAlias
from urllib.parse import urlsplit, urlunsplit

from entari_plugin_htmlrender.errors import InvalidRenderInputError

from .headers import validate_request_header_name, validate_request_header_value

PublicationLeaseId = NewType("PublicationLeaseId", str)


def _invalid_value(
    message: str,
    *,
    operation: str,
    field: str,
    source: BaseException | None = None,
) -> InvalidRenderInputError:
    return InvalidRenderInputError(
        message,
        operation=operation,
        field=field,
        source=source,
    )


def _validate_media_type(
    value: object,
    *,
    operation: str,
) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise _invalid_value(
            "Resource media type must be a non-empty string or None.",
            operation=operation,
            field="media_type",
        )


@dataclass(frozen=True, slots=True)
class PublishedResource:
    """A published asset URL bundled with the exact request authorization.

    ``request_headers`` are the headers a consumer must send to fetch this
    specific URL. The authorization travels with the URL so callers never
    infer it from host, path prefix or network location.  Both the URL and
    headers are valid only while the ``ResourceAccess.publish()`` context that
    yielded this value remains open.
    """

    url: str
    request_headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.url, str):
            raise _invalid_value(
                "Published resource URL must be a string.",
                operation="create_published_resource",
                field="url",
            )
        try:
            parsed = urlsplit(self.url)
        except ValueError as error:
            raise _invalid_value(
                "Published resource URL is malformed.",
                operation="create_published_resource",
                field="url",
                source=error,
            ) from error
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise _invalid_value(
                "Published resources require an absolute http:// or https:// URL.",
                operation="create_published_resource",
                field="url",
            )
        if not isinstance(self.request_headers, Mapping):
            raise _invalid_value(
                "Published resource headers must be a mapping.",
                operation="create_published_resource",
                field="request_headers",
            )
        try:
            headers = dict(self.request_headers)
        except Exception as error:
            raise _invalid_value(
                "Published resource headers could not be copied.",
                operation="create_published_resource",
                field="request_headers",
                source=error,
            ) from error
        if any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in headers.items()
        ):
            raise _invalid_value(
                "Published resource headers must map strings to strings.",
                operation="create_published_resource",
                field="request_headers",
            )
        try:
            lowered_names: set[str] = set()
            for name, value in headers.items():
                validate_request_header_name(name)
                validate_request_header_value(value)
                lowered = name.lower()
                if lowered in lowered_names:
                    raise ValueError(
                        "request header names must be unique case-insensitively"
                    )
                lowered_names.add(lowered)
        except ValueError as error:
            raise _invalid_value(
                "Published resource request headers are not valid HTTP fields.",
                operation="create_published_resource",
                field="request_headers",
                source=error,
            ) from error
        object.__setattr__(
            self,
            "request_headers",
            MappingProxyType(headers),
        )


@dataclass(frozen=True, slots=True)
class ResourceRevision:
    """Opaque source revision used by caching readers."""

    token: str

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or not self.token:
            raise _invalid_value(
                "Resource revisions require a non-empty string token.",
                operation="create_resource_revision",
                field="token",
            )


@dataclass(frozen=True, slots=True)
class ResourceContent:
    """One immutable resource snapshot."""

    data: bytes
    media_type: str | None = None
    revision: ResourceRevision | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise _invalid_value(
                "Resource content data must be immutable bytes.",
                operation="create_resource_content",
                field="data",
            )
        _validate_media_type(
            self.media_type,
            operation="create_resource_content",
        )
        if self.revision is not None and not isinstance(
            self.revision, ResourceRevision
        ):
            raise _invalid_value(
                "Resource content revision must be a ResourceRevision or None.",
                operation="create_resource_content",
                field="revision",
            )


@dataclass(frozen=True, slots=True)
class NotModified:
    """Typed conditional-read outcome: the cached revision is still current."""

    revision: ResourceRevision

    def __post_init__(self) -> None:
        if not isinstance(self.revision, ResourceRevision):
            raise _invalid_value(
                "NotModified requires a ResourceRevision.",
                operation="create_not_modified",
                field="revision",
            )


@dataclass(frozen=True, slots=True)
class FileResourceRef:
    path: Path

    def __post_init__(self) -> None:
        # Freeze one absolute lexical identity without dereferencing symlinks.
        # Canonicalization and authorization remain atomic at the fetch boundary.
        if not isinstance(self.path, Path):
            raise _invalid_value(
                "File resource reference path must be a pathlib.Path.",
                operation="create_file_resource_ref",
                field="path",
            )
        try:
            normalized = Path(os.path.normpath(self.path)).expanduser().absolute()
        except (OSError, RuntimeError, ValueError) as error:
            raise _invalid_value(
                "File resource reference path could not be normalized.",
                operation="create_file_resource_ref",
                field="path",
                source=error,
            ) from error
        object.__setattr__(self, "path", normalized)

    @property
    def identity(self) -> tuple[str, str]:
        return ("file", str(self.path))


@dataclass(frozen=True, slots=True)
class PackageResourceRef:
    package: str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.package, str) or not self.package.strip():
            raise _invalid_value(
                "Package resource references require a non-empty package name.",
                operation="create_package_resource_ref",
                field="package",
            )
        if not isinstance(self.name, str):
            raise _invalid_value(
                "Package resource logical name must be a string.",
                operation="create_package_resource_ref",
                field="name",
            )
        logical = PurePosixPath(self.name)
        if (
            not logical.parts
            or "\\" in self.name
            or logical.is_absolute()
            or any(part in {"", ".", ".."} for part in logical.parts)
        ):
            raise _invalid_value(
                f"Invalid logical resource name: {self.name!r}",
                operation="create_package_resource_ref",
                field="name",
            )
        object.__setattr__(self, "name", logical.as_posix())

    @property
    def identity(self) -> tuple[str, str, str]:
        return ("package", self.package, self.name)


@dataclass(frozen=True, slots=True)
class RemoteResourceRef:
    url: str

    def __post_init__(self) -> None:
        if not isinstance(self.url, str):
            raise _invalid_value(
                "Remote resource URL must be a string.",
                operation="create_remote_resource_ref",
                field="url",
            )
        try:
            parsed = urlsplit(self.url)
            port = parsed.port
        except ValueError as error:
            raise _invalid_value(
                "Remote resource URL is malformed.",
                operation="create_remote_resource_ref",
                field="url",
                source=error,
            ) from error
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        if scheme not in {"http", "https"} or not parsed.netloc or hostname is None:
            raise _invalid_value(
                "Remote resources must use an absolute http:// or https:// URL.",
                operation="create_remote_resource_ref",
                field="url",
            )
        if parsed.username is not None or parsed.password is not None:
            raise _invalid_value(
                "Remote resource URLs must not contain user information.",
                operation="create_remote_resource_ref",
                field="url",
            )
        if port == 0 or parsed.netloc.endswith(":"):
            raise _invalid_value(
                "Remote resource URL port must be between 1 and 65535.",
                operation="create_remote_resource_ref",
                field="url",
            )

        normalized_host = hostname.lower()
        if ":" in normalized_host:
            normalized_host = f"[{normalized_host}]"
        default_port = 80 if scheme == "http" else 443
        normalized_netloc = (
            normalized_host
            if port is None or port == default_port
            else f"{normalized_host}:{port}"
        )
        object.__setattr__(
            self,
            "url",
            urlunsplit(
                (
                    scheme,
                    normalized_netloc,
                    parsed.path or "/",
                    parsed.query,
                    "",
                )
            ),
        )

    @property
    def identity(self) -> tuple[str, str]:
        return ("remote", self.url)


@dataclass(frozen=True, slots=True)
class InlineResource:
    """Caller-owned bytes that need no source lookup.

    Inline data is deliberately not a :class:`ResourceRef`: references locate
    content, while this value already *is* content.  Keeping it outside the
    locator union prevents caches and access policies from pretending that an
    in-memory payload has a filesystem or network identity.
    """

    data: bytes
    media_type: str | None = None
    _digest: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise _invalid_value(
                "Inline resource data must be immutable bytes.",
                operation="create_inline_resource",
                field="data",
            )
        _validate_media_type(
            self.media_type,
            operation="create_inline_resource",
        )
        object.__setattr__(self, "_digest", sha256(self.data).digest())

    @property
    def digest(self) -> str:
        return self._digest.hex()

    @property
    def identity(self) -> tuple[str, bytes, int, str | None]:
        return ("inline", self._digest, len(self.data), self.media_type)


ResourceRef: TypeAlias = FileResourceRef | PackageResourceRef | RemoteResourceRef


__all__ = [
    "FileResourceRef",
    "InlineResource",
    "NotModified",
    "PackageResourceRef",
    "PublicationLeaseId",
    "PublishedResource",
    "RemoteResourceRef",
    "ResourceContent",
    "ResourceRef",
    "ResourceRevision",
]
