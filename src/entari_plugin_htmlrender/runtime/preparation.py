"""Validated preparation calls sharing the runtime's admission and drain boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from entari_plugin_htmlrender.preparation.models import TemplateRef
from entari_plugin_htmlrender.resources.models import (
    FileResourceRef,
    PackageResourceRef,
    RemoteResourceRef,
)

from .renderer import (
    _invalid,
    _snapshot_template_options,
    _snapshot_variables,
    _validate_policy,
    _validate_reference,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from entari_plugin_htmlrender.preparation.models import PreparedHtml
    from entari_plugin_htmlrender.preparation.service import HtmlPreparer
    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.resources.config import ResourceMaterializationPolicy
    from entari_plugin_htmlrender.resources.models import ResourceRef
    from entari_plugin_htmlrender.resources.templating import (
        ExtensionSpec,
        FilterCallable,
    )


@final
class _AdmittedHtmlPreparer:
    """Keep retained preparation facades valid only while their runtime is open."""

    def __init__(
        self,
        delegate: HtmlPreparer,
        admission: OperationAdmissionGate,
    ) -> None:
        self._delegate = delegate
        self._admission = admission

    async def prepare_html(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> PreparedHtml:
        operation = "preparation.html"
        async with self._admission.operation(operation):
            if not isinstance(html, str):
                raise _invalid(operation, "html", "html must be a string.")
            if base_url is not None and not isinstance(base_url, str):
                raise _invalid(
                    operation, "base_url", "base_url must be a string or None."
                )
            return await self._delegate.prepare_html(html, base_url=base_url)

    async def prepare_text(
        self,
        text: str,
        *,
        stylesheet: ResourceRef | None = None,
    ) -> PreparedHtml:
        operation = "preparation.text"
        async with self._admission.operation(operation):
            if not isinstance(text, str):
                raise _invalid(operation, "text", "text must be a string.")
            stylesheet = _validate_reference(operation, "stylesheet", stylesheet)
            return await self._delegate.prepare_text(text, stylesheet=stylesheet)

    async def prepare_markdown(
        self,
        source: str | ResourceRef,
        *,
        stylesheet: ResourceRef | None = None,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml:
        operation = "preparation.markdown"
        async with self._admission.operation(operation):
            if not isinstance(
                source, (str, FileResourceRef, PackageResourceRef, RemoteResourceRef)
            ):
                raise _invalid(
                    operation,
                    "source",
                    "source must be inline Markdown or a ResourceRef value.",
                )
            stylesheet = _validate_reference(operation, "stylesheet", stylesheet)
            materialization_policy = _validate_policy(operation, materialization_policy)
            return await self._delegate.prepare_markdown(
                source,
                stylesheet=stylesheet,
                materialization_policy=materialization_policy,
            )

    async def prepare_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
        *,
        filters: Mapping[str, FilterCallable] | None = None,
        extensions: Sequence[ExtensionSpec] = (),
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml:
        operation = "preparation.template"
        async with self._admission.operation(operation):
            if not isinstance(template, TemplateRef):
                raise _invalid(
                    operation, "template", "template must be a TemplateRef value."
                )
            snapshot = _snapshot_variables(operation, variables)
            filters, extensions = _snapshot_template_options(
                operation, filters, extensions
            )
            materialization_policy = _validate_policy(operation, materialization_policy)
            return await self._delegate.prepare_template(
                template,
                snapshot,
                filters=filters,
                extensions=extensions,
                materialization_policy=materialization_policy,
            )

    async def render_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
        *,
        filters: Mapping[str, FilterCallable] | None = None,
        extensions: Sequence[ExtensionSpec] = (),
    ) -> str:
        operation = "preparation.render_template"
        async with self._admission.operation(operation):
            if not isinstance(template, TemplateRef):
                raise _invalid(
                    operation, "template", "template must be a TemplateRef value."
                )
            filters, extensions = _snapshot_template_options(
                operation, filters, extensions
            )
            return await self._delegate.render_template(
                template,
                _snapshot_variables(operation, variables),
                filters=filters,
                extensions=extensions,
            )


__all__: list[str] = []
