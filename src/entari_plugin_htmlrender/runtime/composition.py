"""Framework-neutral assembly of the runtime application layer."""

from __future__ import annotations

from entari_plugin_htmlrender.errors import ProviderConfigurationError

# Public composition annotations remain available to runtime introspection.
from entari_plugin_htmlrender.graphics.ports import GraphicsRenderer  # noqa: TC001
from entari_plugin_htmlrender.preparation.service import HtmlPreparer  # noqa: TC001
from entari_plugin_htmlrender.providers.sdk import ProviderBinding  # noqa: TC001
from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
from entari_plugin_htmlrender.rendering.budget import (
    BudgetedPreparedHtmlExecutor,
    HtmlRenderBudget,
)
from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog
from entari_plugin_htmlrender.rendering.ports import (  # noqa: TC001
    PreparedHtmlExecutor,
)
from entari_plugin_htmlrender.resources.ports import ResourceAccess  # noqa: TC001

from .bindings import _HtmlRendererBindings
from .renderer import _DefaultHtmlRenderer, _DefaultTemplateRenderer
from .runtime import RenderRuntime
from .use_cases import (
    _RasterizeHtml,
    _RasterizeMarkdown,
    _RasterizePrepared,
    _RasterizeTemplate,
    _RasterizeText,
    _RenderTemplate,
)


def _build_renderer_bindings(
    *,
    executor: PreparedHtmlExecutor | None,
    preparer: HtmlPreparer,
    provider_id: str | None,
    html_render_budget: HtmlRenderBudget | None,
) -> _HtmlRendererBindings:
    if executor is None:
        return _HtmlRendererBindings()
    if provider_id is None:
        raise ProviderConfigurationError(
            "provider_id is required when an executor is configured.",
            provider_id=None,
            operation="build_runtime",
        )

    budgeted_executor = BudgetedPreparedHtmlExecutor(
        executor,
        html_render_budget or HtmlRenderBudget(),
        provider_id=provider_id,
    )
    return _HtmlRendererBindings(
        rasterize_html=_RasterizeHtml(
            preparer=preparer,
            executor=budgeted_executor,
        ),
        rasterize_text=_RasterizeText(
            preparer=preparer,
            executor=budgeted_executor,
        ),
        rasterize_markdown=_RasterizeMarkdown(
            preparer=preparer,
            executor=budgeted_executor,
        ),
        rasterize_template=_RasterizeTemplate(
            preparer=preparer,
            executor=budgeted_executor,
        ),
        rasterize_prepared=_RasterizePrepared(executor=budgeted_executor),
    )


def build_runtime(
    *,
    binding: ProviderBinding,
    provider_id: str | None,
    preparer: HtmlPreparer,
    resources: ResourceAccess,
    graphics: GraphicsRenderer,
    operation_admission: OperationAdmissionGate | None = None,
    capabilities: CapabilityCatalog | None = None,
    html_render_budget: HtmlRenderBudget | None = None,
) -> RenderRuntime:
    """Assemble one host-neutral runtime without acquiring external resources."""
    admission = operation_admission or OperationAdmissionGate()
    bindings = _build_renderer_bindings(
        executor=binding.prepared_html_executor,
        preparer=preparer,
        provider_id=provider_id,
        html_render_budget=html_render_budget,
    )
    catalog = binding.provider_capabilities or CapabilityCatalog()
    if capabilities is not None:
        catalog = catalog.merged(capabilities)
    return RenderRuntime(
        renderer=_DefaultHtmlRenderer(
            bindings,
            operation_admission=admission,
            provider_id=provider_id,
        ),
        templates=_DefaultTemplateRenderer(
            _RenderTemplate(preparer=preparer),
            operation_admission=admission,
            provider_id=provider_id,
        ),
        resources=resources,
        graphics=graphics,
        lifecycle=binding.lifecycle,
        capabilities=catalog,
        operation_admission=admission,
        provider_id=provider_id,
    )


__all__ = ["build_runtime"]
