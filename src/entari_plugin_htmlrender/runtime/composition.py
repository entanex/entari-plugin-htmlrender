"""Assembly of a host-neutral render runtime from engine bindings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
from entari_plugin_htmlrender.rendering.budget import (
    BudgetedPreparedHtmlExecutor,
    HtmlRenderBudget,
)
from entari_plugin_htmlrender.rendering.capabilities import CapabilityCatalog

from .bindings import HtmlRendererBindings
from .renderer import HtmlRenderer
from .runtime import RenderRuntime
from .use_cases import (
    RasterizeHtml,
    RenderHtml,
    RenderMarkdown,
    RenderTemplate,
    RenderTemplateHtml,
    RenderText,
)

if TYPE_CHECKING:
    from entari_plugin_htmlrender.preparation.service import HtmlPreparer
    from entari_plugin_htmlrender.providers.sdk import EngineBindings
    from entari_plugin_htmlrender.rendering.ports import PreparedHtmlExecutor
    from entari_plugin_htmlrender.resources.service import ResourceService


def build_html_renderer_bindings(
    *,
    executor: PreparedHtmlExecutor | None,
    preparer: HtmlPreparer,
    html_render_budget: HtmlRenderBudget | None = None,
) -> HtmlRendererBindings:
    """Derive use-case bindings from what the engine actually provides.

    Without an executor only the html-producing use case is available;
    renderer capabilities follow from the bindings, never from declarations.
    """
    template_html = RenderTemplateHtml(preparer=preparer)
    if executor is None:
        return HtmlRendererBindings(render_template_html=template_html)
    budgeted_executor = BudgetedPreparedHtmlExecutor(
        executor,
        html_render_budget or HtmlRenderBudget(),
    )
    return HtmlRendererBindings(
        render_html=RenderHtml(preparer=preparer, executor=budgeted_executor),
        render_text=RenderText(preparer=preparer, executor=budgeted_executor),
        render_markdown=RenderMarkdown(preparer=preparer, executor=budgeted_executor),
        render_template=RenderTemplate(preparer=preparer, executor=budgeted_executor),
        render_template_html=template_html,
        rasterize_html=RasterizeHtml(executor=budgeted_executor),
    )


def build_runtime(
    *,
    engine: EngineBindings,
    preparer: HtmlPreparer,
    resources: ResourceService,
    operation_admission: OperationAdmissionGate | None = None,
    extensions: CapabilityCatalog | None = None,
    html_render_budget: HtmlRenderBudget | None = None,
) -> RenderRuntime:
    """Assemble a RenderRuntime around one composed engine."""
    admission = (
        operation_admission
        if operation_admission is not None
        else OperationAdmissionGate()
    )
    # Admission is counted exactly once per public entry point: HtmlRenderer
    # wraps its use cases and RenderRuntime wraps retained facades, so bindings
    # here MUST receive the raw (unadmitted) preparer to avoid double counting.
    bindings = build_html_renderer_bindings(
        executor=engine.prepared_html_executor,
        preparer=preparer,
        html_render_budget=html_render_budget,
    )
    runtime_extensions = (
        engine.provider_capabilities
        if engine.provider_capabilities is not None
        else CapabilityCatalog()
    )
    if extensions is not None:
        runtime_extensions = runtime_extensions.merged(extensions)
    return RenderRuntime(
        renderer=HtmlRenderer(bindings, operation_admission=admission),
        preparation=preparer,
        resources=resources,
        lifecycle=engine.lifecycle,
        extensions=runtime_extensions,
        operation_admission=admission,
    )


__all__ = ["build_html_renderer_bindings", "build_runtime"]
