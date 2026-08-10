"""Prepare arbitrary HTML while preserving browser and native execution forms."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

from entari_plugin_htmlrender.errors import InvalidRenderInputError

from .models import (
    DocumentBase,
    DocumentRequirement,
    DocumentStructureSnapshot,
    PreparedAsset,
    PreparedHtml,
    PreparedStylesheet,
)
from .references import css_resource_references, inspect_html_references

if TYPE_CHECKING:
    from collections.abc import Iterable


def _resource_requirement(
    value: str,
    *,
    base_url: str | None,
) -> DocumentRequirement | None:
    stripped = value.strip()
    if not stripped or stripped.startswith(("data:", "memory:", "#")):
        return None
    resolved = urljoin(base_url, stripped) if base_url else stripped
    parsed = urlsplit(resolved)
    if parsed.scheme in {"http", "https"}:
        return DocumentRequirement.NETWORK
    if parsed.scheme == "file" or not parsed.scheme:
        return DocumentRequirement.LOCAL_RESOURCE
    return None


def _normalize_stylesheet(
    stylesheet: str | PreparedStylesheet,
    *,
    base_url: str | None,
) -> PreparedStylesheet:
    if isinstance(stylesheet, PreparedStylesheet):
        return stylesheet
    return PreparedStylesheet(css=stylesheet, base_url=base_url)


def _prepare_html(
    html: str,
    *,
    base_url: str | None = None,
    stylesheets: Iterable[str | PreparedStylesheet] = (),
    assets: Iterable[PreparedAsset] = (),
) -> PreparedHtml:
    """Build a canonical payload without performing backend-specific transport."""

    try:
        inspected = inspect_html_references(html, base_url=base_url)
    except (TypeError, ValueError) as error:
        raise InvalidRenderInputError(
            "HTML source could not be parsed.",
            operation="html.parse",
            field="html",
            source=error,
        ) from error
    # The single place that parses the markup; materialization and adapters
    # read ``PreparedHtml.document_base``/``structure`` instead of re-parsing.
    document_base_value = DocumentBase(
        declared_href=inspected.base_href,
        preparation_base_url=base_url,
    )
    try:
        document_base = document_base_value.resolve()
    except (TypeError, ValueError) as error:
        raise InvalidRenderInputError(
            "HTML document base could not be resolved.",
            operation="html.parse",
            field="html",
            source=error,
        ) from error
    external_stylesheets = tuple(
        _normalize_stylesheet(stylesheet, base_url=base_url)
        for stylesheet in stylesheets
    )
    embedded_stylesheets = tuple(
        PreparedStylesheet(
            css=stylesheet.css,
            base_url=document_base,
            embedded=True,
            media=stylesheet.media,
        )
        for stylesheet in inspected.stylesheets
    )
    stylesheet_snapshot = (*external_stylesheets, *embedded_stylesheets)
    requirements: set[DocumentRequirement] = set()

    if inspected.has_script:
        requirements.add(DocumentRequirement.JAVASCRIPT)
    try:
        for reference in inspected.references:
            requirement = _resource_requirement(reference, base_url=document_base)
            if requirement is not None:
                requirements.add(requirement)
    except (TypeError, ValueError) as error:
        raise InvalidRenderInputError(
            "HTML resource reference could not be resolved.",
            operation="html.parse",
            field="html",
            source=error,
        ) from error
    try:
        for stylesheet in external_stylesheets:
            for reference in css_resource_references(stylesheet.css):
                requirement = _resource_requirement(
                    reference,
                    base_url=stylesheet.base_url,
                )
                if requirement is not None:
                    requirements.add(requirement)
    except (TypeError, ValueError) as error:
        raise InvalidRenderInputError(
            "Stylesheet resource reference could not be resolved.",
            operation="html.parse",
            field="stylesheets",
            source=error,
        ) from error

    return PreparedHtml(
        html=html,
        stylesheets=stylesheet_snapshot,
        assets=tuple(assets),
        requirements=frozenset(requirements),
        document_base=document_base_value,
        structure=DocumentStructureSnapshot(
            references=tuple(inspected.references),
            linked_stylesheets=tuple(inspected.linked_stylesheets),
            has_script=inspected.has_script,
            base_tag=inspected.base_tag,
            head_open_end=inspected.head_open_end,
            doctype_end=inspected.doctype_end,
        ),
    )


def parse_html(
    html: str,
    *,
    base_url: str | None = None,
    stylesheets: Iterable[str | PreparedStylesheet] = (),
    assets: Iterable[PreparedAsset] = (),
) -> PreparedHtml:
    """Build a canonical payload without performing backend-specific transport."""
    if not isinstance(html, str):
        raise InvalidRenderInputError(
            "HTML source must be a string.",
            operation="html.parse",
            field="html",
        )
    if base_url is not None and not isinstance(base_url, str):
        raise InvalidRenderInputError(
            "HTML base URL must be a string or None.",
            operation="html.parse",
            field="base_url",
        )
    if base_url is not None:
        try:
            urlsplit(base_url)
        except ValueError as error:
            raise InvalidRenderInputError(
                "HTML base URL could not be parsed.",
                operation="html.parse",
                field="base_url",
                source=error,
            ) from error
    try:
        stylesheet_snapshot = tuple(stylesheets)
    except (TypeError, ValueError) as error:
        raise InvalidRenderInputError(
            "stylesheets must be an iterable of strings or PreparedStylesheet values.",
            operation="html.parse",
            field="stylesheets",
            source=error,
        ) from error
    if not all(
        isinstance(stylesheet, (str, PreparedStylesheet))
        for stylesheet in stylesheet_snapshot
    ):
        raise InvalidRenderInputError(
            "stylesheets must contain only strings or PreparedStylesheet values.",
            operation="html.parse",
            field="stylesheets",
        )
    try:
        asset_snapshot = tuple(assets)
    except (TypeError, ValueError) as error:
        raise InvalidRenderInputError(
            "assets must be an iterable of PreparedAsset values.",
            operation="html.parse",
            field="assets",
            source=error,
        ) from error
    if not all(isinstance(asset, PreparedAsset) for asset in asset_snapshot):
        raise InvalidRenderInputError(
            "assets must contain only PreparedAsset values.",
            operation="html.parse",
            field="assets",
        )
    try:
        return _prepare_html(
            html,
            base_url=base_url,
            stylesheets=stylesheet_snapshot,
            assets=asset_snapshot,
        )
    except InvalidRenderInputError:
        raise
    except (TypeError, ValueError) as error:
        raise InvalidRenderInputError(
            "HTML input could not be parsed.",
            operation="html.parse",
            field="html",
            source=error,
        ) from error


__all__ = ("parse_html",)
