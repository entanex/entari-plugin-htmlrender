"""Public renderer facade over the injected use-case bindings."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, final

from entari_plugin_htmlrender.rendering.errors import CapabilityUnavailable
from entari_plugin_htmlrender.rendering.requests import RenderCommand

if TYPE_CHECKING:
    from entari_plugin_htmlrender.rendering.admission import OperationAdmissionGate
    from entari_plugin_htmlrender.rendering.artifacts import (
        RenderedHtml,
        RenderedImage,
    )
    from entari_plugin_htmlrender.rendering.requests import (
        RasterizeHtmlRequest,
        RenderHtmlRequest,
        RenderMarkdownRequest,
        RenderTemplateHtmlRequest,
        RenderTemplateRequest,
        RenderTextRequest,
    )

    from .bindings import HtmlRendererBindings

_BindingT = TypeVar("_BindingT")


@final
class HtmlRenderer:
    """Executes render commands through explicitly injected use cases."""

    def __init__(
        self,
        bindings: HtmlRendererBindings,
        *,
        operation_admission: OperationAdmissionGate,
    ) -> None:
        self._bindings = bindings
        self._operation_admission = operation_admission

    @property
    def supported_commands(self) -> frozenset[RenderCommand]:
        """Portable commands derived from the bound use cases."""
        return self._bindings.present()

    def supports(self, command: RenderCommand) -> bool:
        if not isinstance(command, RenderCommand):
            raise TypeError("command must be a RenderCommand value.")
        return command in self._bindings.present()

    @staticmethod
    def _require(binding: _BindingT | None, command: RenderCommand) -> _BindingT:
        if binding is None:
            raise CapabilityUnavailable(command.value)
        return binding

    async def render_html(self, request: RenderHtmlRequest) -> RenderedImage:
        use_case = self._require(self._bindings.render_html, RenderCommand.HTML)
        async with self._operation_admission.operation():
            return await use_case.execute(request)

    async def render_text(self, request: RenderTextRequest) -> RenderedImage:
        use_case = self._require(self._bindings.render_text, RenderCommand.TEXT)
        async with self._operation_admission.operation():
            return await use_case.execute(request)

    async def render_markdown(self, request: RenderMarkdownRequest) -> RenderedImage:
        use_case = self._require(self._bindings.render_markdown, RenderCommand.MARKDOWN)
        async with self._operation_admission.operation():
            return await use_case.execute(request)

    async def render_template(self, request: RenderTemplateRequest) -> RenderedImage:
        use_case = self._require(self._bindings.render_template, RenderCommand.TEMPLATE)
        async with self._operation_admission.operation():
            return await use_case.execute(request)

    async def render_template_html(
        self,
        request: RenderTemplateHtmlRequest,
    ) -> RenderedHtml:
        use_case = self._require(
            self._bindings.render_template_html,
            RenderCommand.TEMPLATE_HTML,
        )
        async with self._operation_admission.operation():
            return await use_case.execute(request)

    async def rasterize_html(self, request: RasterizeHtmlRequest) -> RenderedImage:
        use_case = self._require(
            self._bindings.rasterize_html,
            RenderCommand.RASTERIZE_HTML,
        )
        async with self._operation_admission.operation():
            return await use_case.execute(request)
