"""Private default implementations of the public rendering contracts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import math
from types import MappingProxyType
from typing import TYPE_CHECKING, TypeVar, final

import anyio

from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    RenderTimeoutError,
    UnsupportedOperationError,
)
from entari_plugin_htmlrender.preparation.models import (
    PreparedHtml,
    RasterOptions,
    TemplateRef,
)
from entari_plugin_htmlrender.rendering.contracts import (
    HtmlRenderer as HtmlRenderer,
)
from entari_plugin_htmlrender.rendering.contracts import (
    TemplateRenderer as TemplateRenderer,
)
from entari_plugin_htmlrender.rendering.models import RenderOperation
from entari_plugin_htmlrender.resources.config import ResourceMaterializationPolicy
from entari_plugin_htmlrender.resources.models import (
    FileResourceRef,
    PackageResourceRef,
    RemoteResourceRef,
    ResourceRef,
)

if TYPE_CHECKING:
    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.artifacts import (
        RenderedHtml,
        RenderedImage,
    )

    from .bindings import _HtmlRendererBindings
    from .use_cases import _RenderTemplate

_BindingT = TypeVar("_BindingT")
_RESOURCE_REFERENCE_TYPES = (
    FileResourceRef,
    PackageResourceRef,
    RemoteResourceRef,
)
_DEFAULT_RASTER_OPTIONS = RasterOptions()


def _invalid(
    operation: str,
    field: str,
    message: str,
) -> InvalidRenderInputError:
    return InvalidRenderInputError(
        message,
        operation=operation,
        field=field,
    )


def _validate_timeout(operation: str, timeout_seconds: float | None) -> None:
    if timeout_seconds is not None and (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise _invalid(
            operation,
            "timeout_seconds",
            "timeout_seconds must be finite and positive when provided.",
        )


def _validate_raster(operation: str, raster: object) -> RasterOptions:
    if not isinstance(raster, RasterOptions):
        raise _invalid(
            operation,
            "raster",
            "raster must be a RasterOptions value.",
        )
    return raster


def _validate_policy(
    operation: str,
    policy: object,
) -> ResourceMaterializationPolicy | None:
    if policy is not None and not isinstance(policy, ResourceMaterializationPolicy):
        raise _invalid(
            operation,
            "materialization_policy",
            "materialization_policy must be a ResourceMaterializationPolicy value.",
        )
    return policy


def _validate_reference(
    operation: str,
    field: str,
    reference: object,
) -> ResourceRef | None:
    if reference is not None and not isinstance(
        reference,
        _RESOURCE_REFERENCE_TYPES,
    ):
        raise _invalid(
            operation,
            field,
            f"{field} must be a ResourceRef value or None.",
        )
    return reference


def _snapshot_variables(
    operation: str,
    variables: Mapping[str, object] | None,
) -> Mapping[str, object]:
    if variables is None:
        return MappingProxyType({})
    if not isinstance(variables, Mapping) or any(
        not isinstance(key, str) for key in variables
    ):
        raise _invalid(
            operation,
            "variables",
            "variables must be a mapping with string keys.",
        )
    return MappingProxyType(dict(variables))


@contextmanager
def _operation_deadline(
    operation: str,
    timeout_seconds: float | None,
) -> Iterator[None]:
    _validate_timeout(operation, timeout_seconds)
    if timeout_seconds is None:
        yield
        return

    cancel_scope: anyio.CancelScope | None = None
    try:
        with anyio.fail_after(timeout_seconds) as cancel_scope:
            yield
    except TimeoutError as error:
        if cancel_scope is None or not cancel_scope.cancel_called:
            raise
        raise RenderTimeoutError(
            operation,
            timeout_seconds,
            source=error,
        ) from error


@final
class _DefaultHtmlRenderer:
    """Composition-owned implementation hidden behind :class:`HtmlRenderer`."""

    def __init__(
        self,
        bindings: _HtmlRendererBindings,
        *,
        operation_admission: OperationAdmissionGate,
        provider_id: str | None = None,
    ) -> None:
        self._bindings = bindings
        self._operation_admission = operation_admission
        self._provider_id = provider_id

    @property
    def supported_operations(self) -> frozenset[RenderOperation]:
        return self._bindings.supported_operations()

    def supports(self, operation: RenderOperation) -> bool:
        if not isinstance(operation, RenderOperation):
            raise _invalid(
                "supports",
                "operation",
                "operation must be a RenderOperation value.",
            )
        return operation in self._bindings.supported_operations()

    def _require(
        self,
        binding: _BindingT | None,
        operation: str,
    ) -> _BindingT:
        if binding is None:
            raise UnsupportedOperationError(
                operation,
                provider_id=self._provider_id,
            )
        return binding

    async def rasterize_html(
        self,
        html: str,
        *,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        base_url: str | None = None,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage:
        operation = RenderOperation.HTML_TO_IMAGE.value
        self._operation_admission.ensure_accepting(operation)
        if not isinstance(html, str):
            raise _invalid(operation, "html", "html must be a string.")
        if base_url is not None and not isinstance(base_url, str):
            raise _invalid(operation, "base_url", "base_url must be a string or None.")
        raster = _validate_raster(operation, raster)
        materialization_policy = _validate_policy(
            operation,
            materialization_policy,
        )
        with _operation_deadline(operation, timeout_seconds):
            async with self._operation_admission.operation(operation):
                use_case = self._require(self._bindings.rasterize_html, operation)
                return await use_case.execute(
                    html,
                    raster=raster,
                    base_url=base_url,
                    materialization_policy=materialization_policy,
                )

    async def rasterize_text(
        self,
        text: str,
        *,
        stylesheet: ResourceRef | None = None,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage:
        operation = RenderOperation.TEXT_TO_IMAGE.value
        self._operation_admission.ensure_accepting(operation)
        if not isinstance(text, str):
            raise _invalid(operation, "text", "text must be a string.")
        stylesheet = _validate_reference(operation, "stylesheet", stylesheet)
        raster = _validate_raster(operation, raster)
        materialization_policy = _validate_policy(
            operation,
            materialization_policy,
        )
        with _operation_deadline(operation, timeout_seconds):
            async with self._operation_admission.operation(operation):
                use_case = self._require(self._bindings.rasterize_text, operation)
                return await use_case.execute(
                    text,
                    stylesheet=stylesheet,
                    raster=raster,
                    materialization_policy=materialization_policy,
                )

    async def rasterize_markdown(
        self,
        source: str | ResourceRef,
        *,
        stylesheet: ResourceRef | None = None,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage:
        operation = RenderOperation.MARKDOWN_TO_IMAGE.value
        self._operation_admission.ensure_accepting(operation)
        if not isinstance(source, (str, *_RESOURCE_REFERENCE_TYPES)):
            raise _invalid(
                operation,
                "source",
                "source must be inline Markdown or a ResourceRef value.",
            )
        stylesheet = _validate_reference(operation, "stylesheet", stylesheet)
        raster = _validate_raster(operation, raster)
        materialization_policy = _validate_policy(
            operation,
            materialization_policy,
        )
        with _operation_deadline(operation, timeout_seconds):
            async with self._operation_admission.operation(operation):
                use_case = self._require(
                    self._bindings.rasterize_markdown,
                    operation,
                )
                return await use_case.execute(
                    source,
                    stylesheet=stylesheet,
                    raster=raster,
                    materialization_policy=materialization_policy,
                )

    async def rasterize_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object] | None = None,
        *,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage:
        operation = RenderOperation.TEMPLATE_TO_IMAGE.value
        self._operation_admission.ensure_accepting(operation)
        if not isinstance(template, TemplateRef):
            raise _invalid(
                operation,
                "template",
                "template must be a TemplateRef value.",
            )
        variables = _snapshot_variables(operation, variables)
        raster = _validate_raster(operation, raster)
        materialization_policy = _validate_policy(
            operation,
            materialization_policy,
        )
        with _operation_deadline(operation, timeout_seconds):
            async with self._operation_admission.operation(operation):
                use_case = self._require(
                    self._bindings.rasterize_template,
                    operation,
                )
                return await use_case.execute(
                    template,
                    variables,
                    raster=raster,
                    materialization_policy=materialization_policy,
                )

    async def rasterize_prepared(
        self,
        prepared: PreparedHtml,
        *,
        raster: RasterOptions = _DEFAULT_RASTER_OPTIONS,
        materialization_policy: ResourceMaterializationPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> RenderedImage:
        operation = RenderOperation.PREPARED_HTML_TO_IMAGE.value
        self._operation_admission.ensure_accepting(operation)
        if not isinstance(prepared, PreparedHtml):
            raise _invalid(
                operation,
                "prepared",
                "prepared must be a PreparedHtml value.",
            )
        raster = _validate_raster(operation, raster)
        materialization_policy = _validate_policy(
            operation,
            materialization_policy,
        )
        with _operation_deadline(operation, timeout_seconds):
            async with self._operation_admission.operation(operation):
                use_case = self._require(
                    self._bindings.rasterize_prepared,
                    operation,
                )
                return await use_case.execute(
                    prepared,
                    raster=raster,
                    materialization_policy=materialization_policy,
                )


@final
class _DefaultTemplateRenderer:
    """Composition-owned implementation hidden behind :class:`TemplateRenderer`."""

    def __init__(
        self,
        use_case: _RenderTemplate | None,
        *,
        operation_admission: OperationAdmissionGate,
        provider_id: str | None = None,
    ) -> None:
        self._use_case = use_case
        self._operation_admission = operation_admission
        self._provider_id = provider_id

    async def render(
        self,
        template: TemplateRef,
        variables: Mapping[str, object] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> RenderedHtml:
        operation = RenderOperation.TEMPLATE_TO_HTML.value
        self._operation_admission.ensure_accepting(operation)
        if not isinstance(template, TemplateRef):
            raise _invalid(
                operation,
                "template",
                "template must be a TemplateRef value.",
            )
        variables = _snapshot_variables(operation, variables)
        with _operation_deadline(operation, timeout_seconds):
            async with self._operation_admission.operation(operation):
                if self._use_case is None:
                    raise UnsupportedOperationError(
                        operation,
                        provider_id=self._provider_id,
                    )
                use_case = self._use_case
                return await use_case.execute(template, variables)


__all__ = ["HtmlRenderer", "TemplateRenderer"]
