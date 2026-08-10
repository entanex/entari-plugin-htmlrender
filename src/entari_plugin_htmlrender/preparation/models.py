"""Backend-neutral documents produced before renderer-specific execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import os
from pathlib import Path, PurePosixPath
import re

from entari_plugin_htmlrender.errors import InvalidRenderInputError

# Keep public annotations resolvable through typing.get_type_hints().
from entari_plugin_htmlrender.raster import RasterImageFormat  # noqa: TC001

from .assets import resolve_document_reference

_MEDIA_TYPE_PATTERN = re.compile(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+")


def _invalid_value(
    operation: str,
    field: str,
    message: str,
    *,
    source: BaseException | None = None,
) -> InvalidRenderInputError:
    return InvalidRenderInputError(
        message,
        operation=operation,
        field=field,
        source=source,
    )


class DocumentRequirement(str, Enum):
    """Execution features required by prepared content."""

    JAVASCRIPT = "javascript"
    NETWORK = "network"
    LOCAL_RESOURCE = "local_resource"


@dataclass(frozen=True, slots=True)
class DocumentBase:
    """Resolved document-base semantics carried by a prepared document.

    ``declared_href`` is the value of an in-document ``<base href>`` parsed
    once by ``parse_html``: ``None`` means no ``<base href>`` was declared,
    while an empty string is an explicit ``<base href="">`` that resolves to
    the document URL itself. ``preparation_base_url`` is the base URL the
    document was prepared with. ``resolve`` combines them with an optional
    execution-time fallback so every consumer derives one canonical base
    instead of re-parsing the markup.
    """

    declared_href: str | None = None
    preparation_base_url: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("declared_href", self.declared_href),
            ("preparation_base_url", self.preparation_base_url),
        ):
            if value is not None and not isinstance(value, str):
                raise _invalid_value(
                    "document_base.create",
                    field_name,
                    f"{field_name} must be a string or None.",
                )

    def resolve(self, fallback_base_url: str | None = None) -> str | None:
        if fallback_base_url is not None and not isinstance(fallback_base_url, str):
            raise _invalid_value(
                "document_base.resolve",
                "fallback_base_url",
                "fallback_base_url must be a string or None.",
            )
        root = self.preparation_base_url or fallback_base_url
        if self.declared_href is not None:
            # An explicit empty href resolves to the document URL itself.
            return resolve_document_reference(root, self.declared_href) or root
        return root


@dataclass(frozen=True, slots=True)
class DocumentStructureSnapshot:
    """Structural facts extracted by the single preparation-time HTML parse.

    Offsets index into the exact ``PreparedHtml.html`` string, so execution
    can canonicalize the document base and inject head content by pure
    string splicing without parsing the markup again.
    """

    references: tuple[str, ...] = ()
    linked_stylesheets: tuple[str, ...] = ()
    has_script: bool = False
    base_tag: tuple[int, int, str] | None = None
    """``(start, end, raw)`` span of the first ``<base>`` carrying ``href``."""
    head_open_end: int | None = None
    doctype_end: int | None = None

    def __post_init__(self) -> None:
        for field_name, values in (
            ("references", self.references),
            ("linked_stylesheets", self.linked_stylesheets),
        ):
            if not isinstance(values, tuple) or not all(
                isinstance(value, str) for value in values
            ):
                raise _invalid_value(
                    "document_structure.create",
                    field_name,
                    f"{field_name} must be a tuple of strings.",
                )
        if type(self.has_script) is not bool:
            raise _invalid_value(
                "document_structure.create",
                "has_script",
                "has_script must be a boolean.",
            )
        if self.base_tag is not None:
            valid_base_tag = (
                isinstance(self.base_tag, tuple)
                and len(self.base_tag) == 3
                and type(self.base_tag[0]) is int
                and type(self.base_tag[1]) is int
                and isinstance(self.base_tag[2], str)
                and 0 <= self.base_tag[0] <= self.base_tag[1]
            )
            if not valid_base_tag:
                raise _invalid_value(
                    "document_structure.create",
                    "base_tag",
                    "base_tag must be a valid (start, end, raw) tuple or None.",
                )
        for field_name, value in (
            ("head_open_end", self.head_open_end),
            ("doctype_end", self.doctype_end),
        ):
            if value is not None and (type(value) is not int or value < 0):
                raise _invalid_value(
                    "document_structure.create",
                    field_name,
                    f"{field_name} must be a non-negative integer or None.",
                )


@dataclass(frozen=True, slots=True)
class PreparedAsset:
    """Binary resource addressable by its exact document URL."""

    source: str
    data: bytes
    media_type: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source:
            raise _invalid_value(
                "prepared_asset.create",
                "source",
                "Prepared asset source must be a non-empty string.",
            )
        if not isinstance(self.data, bytes):
            raise _invalid_value(
                "prepared_asset.create",
                "data",
                "Prepared asset data must be immutable bytes.",
            )
        if self.media_type is not None and (
            not isinstance(self.media_type, str)
            or _MEDIA_TYPE_PATTERN.fullmatch(self.media_type) is None
        ):
            raise _invalid_value(
                "prepared_asset.create",
                "media_type",
                "Prepared asset media_type must be a valid type/subtype or None.",
            )


@dataclass(frozen=True, slots=True)
class PreparedStylesheet:
    """One stylesheet with its own resource-resolution base."""

    css: str
    base_url: str | None = None
    embedded: bool = False
    media: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.css, str):
            raise _invalid_value(
                "prepared_stylesheet.create",
                "css",
                "Prepared stylesheet CSS must be a string.",
            )
        if self.base_url is not None and not isinstance(self.base_url, str):
            raise _invalid_value(
                "prepared_stylesheet.create",
                "base_url",
                "Prepared stylesheet base_url must be a string or None.",
            )
        if type(self.embedded) is not bool:
            raise _invalid_value(
                "prepared_stylesheet.create",
                "embedded",
                "Prepared stylesheet embedded must be a boolean.",
            )
        if self.media is not None and (
            not isinstance(self.media, str) or not self.media.strip()
        ):
            raise _invalid_value(
                "prepared_stylesheet.create",
                "media",
                "Prepared stylesheet media must be a non-empty string or None.",
            )


@dataclass(frozen=True, slots=True)
class PreparedHtml:
    """Canonical HTML payload shared by browser and native renderers.

    ``html`` always retains the original browser document. Build instances
    through :func:`entari_plugin_htmlrender.preparation.parse_html` — the
    sole place that parses the markup; ``document_base`` and ``structure``
    are that parse's results and consumers never re-derive them. The
    resource-resolution root lives in ``document_base.preparation_base_url``.
    """

    html: str
    stylesheets: tuple[PreparedStylesheet, ...] = ()
    assets: tuple[PreparedAsset, ...] = ()
    requirements: frozenset[DocumentRequirement] = field(default_factory=frozenset)
    document_base: DocumentBase = field(kw_only=True)
    """Document-base semantics fixed at preparation time.

    Consumers call ``document_base.resolve(fallback_base_url=...)`` instead of
    re-deriving the base from the markup.
    """
    structure: DocumentStructureSnapshot = field(kw_only=True)
    """Reference and insertion-point facts for the exact ``html`` string."""

    def __post_init__(self) -> None:
        if not isinstance(self.html, str):
            raise _invalid_value(
                "prepared_html.create",
                "html",
                "Prepared HTML source must be a string.",
            )
        if not isinstance(self.stylesheets, tuple) or not all(
            isinstance(value, PreparedStylesheet) for value in self.stylesheets
        ):
            raise _invalid_value(
                "prepared_html.create",
                "stylesheets",
                "Prepared HTML stylesheets must be a tuple of PreparedStylesheet.",
            )
        if not isinstance(self.assets, tuple) or not all(
            isinstance(value, PreparedAsset) for value in self.assets
        ):
            raise _invalid_value(
                "prepared_html.create",
                "assets",
                "Prepared HTML assets must be a tuple of PreparedAsset.",
            )
        if not isinstance(self.requirements, frozenset) or not all(
            isinstance(value, DocumentRequirement) for value in self.requirements
        ):
            raise _invalid_value(
                "prepared_html.create",
                "requirements",
                "Prepared HTML requirements must be a frozenset of "
                "DocumentRequirement.",
            )
        if not isinstance(self.document_base, DocumentBase):
            raise _invalid_value(
                "prepared_html.create",
                "document_base",
                "Prepared HTML document_base must be a DocumentBase.",
            )
        if not isinstance(self.structure, DocumentStructureSnapshot):
            raise _invalid_value(
                "prepared_html.create",
                "structure",
                "Prepared HTML structure must be a DocumentStructureSnapshot.",
            )


@dataclass(frozen=True, slots=True)
class TemplateRef:
    """Immutable locator for one filesystem template.

    ``root`` identifies the template collection while ``name`` is a logical,
    POSIX-style name inside that collection.  The reference carries no
    renderer, environment, filters, or other Jinja implementation state.
    """

    root: Path
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path):
            raise InvalidRenderInputError(
                "Template root must be a pathlib.Path.",
                operation="create_template_ref",
                field="root",
            )
        if not isinstance(self.name, str):
            raise InvalidRenderInputError(
                "Template name must be a string.",
                operation="create_template_ref",
                field="name",
            )
        logical_name = PurePosixPath(self.name)
        if (
            not logical_name.parts
            or "\\" in self.name
            or logical_name.is_absolute()
            or any(part in {"", ".", ".."} for part in logical_name.parts)
        ):
            raise InvalidRenderInputError(
                "Template name must be a non-empty relative POSIX path.",
                operation="create_template_ref",
                field="name",
            )
        # Freeze caller-relative identity now without resolving symlinks.
        # Canonicalization and authorization remain atomic compiler-boundary work.
        object.__setattr__(
            self,
            "root",
            Path(os.path.normpath(self.root)).expanduser().absolute(),
        )
        object.__setattr__(self, "name", logical_name.as_posix())


@dataclass(frozen=True, slots=True)
class RasterOptions:
    """Portable raster options shared by HTML-capable engines."""

    width: int = 800
    height: int | None = None
    device_pixel_ratio: float = 2.0
    format: RasterImageFormat = "png"
    quality: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.width, int)
            or isinstance(self.width, bool)
            or self.width <= 0
        ):
            raise InvalidRenderInputError(
                "Raster width must be a positive integer.",
                operation="raster.configure",
                field="width",
            )
        if self.height is not None and (
            not isinstance(self.height, int)
            or isinstance(self.height, bool)
            or self.height <= 0
        ):
            raise InvalidRenderInputError(
                "Raster height must be a positive integer or None.",
                operation="raster.configure",
                field="height",
            )
        if (
            not isinstance(self.device_pixel_ratio, (int, float))
            or isinstance(self.device_pixel_ratio, bool)
            or not math.isfinite(self.device_pixel_ratio)
            or self.device_pixel_ratio <= 0
        ):
            raise InvalidRenderInputError(
                "device_pixel_ratio must be finite and positive.",
                operation="raster.configure",
                field="device_pixel_ratio",
            )
        if not isinstance(self.format, str) or self.format not in {"png", "jpeg"}:
            raise InvalidRenderInputError(
                "format must be 'png' or 'jpeg'.",
                operation="raster.configure",
                field="format",
            )
        if self.quality is not None and (
            not isinstance(self.quality, int) or isinstance(self.quality, bool)
        ):
            raise InvalidRenderInputError(
                "quality must be an integer or None.",
                operation="raster.configure",
                field="quality",
            )
        if self.quality is not None and self.format != "jpeg":
            raise InvalidRenderInputError(
                "quality is only supported for JPEG output.",
                operation="raster.configure",
                field="quality",
            )
        if self.quality is not None and not 0 <= self.quality <= 100:
            raise InvalidRenderInputError(
                "quality must be between 0 and 100.",
                operation="raster.configure",
                field="quality",
            )


__all__ = (
    "DocumentBase",
    "DocumentRequirement",
    "DocumentStructureSnapshot",
    "PreparedAsset",
    "PreparedHtml",
    "PreparedStylesheet",
    "RasterOptions",
    "TemplateRef",
)
