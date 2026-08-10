from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, final

import markdown

from entari_plugin_htmlrender.resources.config import ResourceMaterializationPolicy
from entari_plugin_htmlrender.resources.models import (
    FileResourceRef,
    PackageResourceRef,
    RemoteResourceRef,
    ResourceRef,
)
from entari_plugin_htmlrender.resources.source import PackageResourceSource

from .html import parse_html
from .materialize import materialize_local_assets
from .models import PreparedHtml, PreparedStylesheet, TemplateRef
from .template_assets import stage_template_variables

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.resources.ports import (
        PreparationResourceAccess,
        TemplateCompiler,
        WorkerExecutor,
    )

BUILTIN_TEMPLATES = PackageResourceSource("entari_plugin_htmlrender", "templates")
TEXT_TEMPLATES = PackageResourceSource("entari_plugin_htmlrender", "templates/text")
MARKDOWN_TEMPLATES = PackageResourceSource(
    "entari_plugin_htmlrender",
    "templates/markdown",
)


class HtmlPreparer(Protocol):
    async def prepare_html(
        self, html: str, *, base_url: str | None = None
    ) -> PreparedHtml: ...

    async def prepare_text(
        self,
        text: str,
        *,
        stylesheet: ResourceRef | None = None,
    ) -> PreparedHtml: ...

    async def prepare_markdown(
        self,
        source: str | ResourceRef,
        *,
        stylesheet: ResourceRef | None = None,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml: ...

    async def prepare_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
        *,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml: ...

    async def render_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
    ) -> str: ...


@final
class DefaultHtmlPreparer:
    """Fully injected preparation pipeline owned by one RenderRuntime."""

    def __init__(
        self,
        *,
        resources: PreparationResourceAccess,
        templates: TemplateCompiler,
        worker: WorkerExecutor,
    ) -> None:
        self._resources = resources
        self._templates = templates
        self._worker = worker

    def _path_uri(self, path: str | Path, *, directory: bool = False) -> str:
        uri = self._resources.authorize_local(Path(path)).as_uri()
        return f"{uri.rstrip('/')}/" if directory else uri

    async def _builtin(self, name: str) -> str:
        return await self._resources.fetch_text(
            PackageResourceRef(
                BUILTIN_TEMPLATES.package, f"{BUILTIN_TEMPLATES.root}/{name}"
            )
        )

    def _resource_base_url(self, reference: ResourceRef) -> str | None:
        if isinstance(reference, FileResourceRef):
            return self._resources.authorize_local(reference.path).as_uri()
        if isinstance(reference, RemoteResourceRef):
            return reference.url
        return None

    async def prepare_html(
        self, html: str, *, base_url: str | None = None
    ) -> PreparedHtml:
        return await self._worker.run_sync(parse_html, html, base_url=base_url)

    async def prepare_text(
        self,
        text: str,
        *,
        stylesheet: ResourceRef | None = None,
    ) -> PreparedHtml:
        css = (
            await self._resources.fetch_text(stylesheet)
            if stylesheet is not None
            else await self._builtin("text/text.css")
        )
        html = await self._templates.render(
            TEXT_TEMPLATES,
            "text.html",
            {"text": text, "css": ""},
            immutable=True,
        )
        stylesheet_base = (
            await self._worker.run_sync(self._resource_base_url, stylesheet)
            if stylesheet is not None
            else None
        )
        return await self._worker.run_sync(
            parse_html,
            html,
            stylesheets=(PreparedStylesheet(css=css, base_url=stylesheet_base),),
        )

    async def prepare_markdown(
        self,
        source: str | ResourceRef,
        *,
        stylesheet: ResourceRef | None = None,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml:
        if isinstance(source, str):
            markdown_text = source
            markup_base = None
        else:
            markdown_text = await self._resources.fetch_text(source)
            markup_base = await self._worker.run_sync(
                self._resource_base_url,
                source,
            )
        rendered = await self._worker.run_sync(
            markdown.markdown,
            markdown_text,
            extensions=[
                "pymdownx.tasklist",
                "tables",
                "fenced_code",
                "codehilite",
                "mdx_math",
                "pymdownx.tilde",
            ],
            extension_configs={"mdx_math": {"enable_dollar_delimiter": True}},
        )
        extra = ""
        if "math/tex" in rendered:
            katex_css = await self._builtin("markdown/katex/katex.min.b64_fonts.css")
            katex_js = await self._builtin("markdown/katex/katex.min.js")
            mhchem_js = await self._builtin("markdown/katex/mhchem.min.js")
            mathtex_js = await self._builtin(
                "markdown/katex/mathtex-script-type.min.js"
            )
            extra = (
                f'<style type="text/css">{katex_css}</style>'
                f"<script defer>{katex_js}</script>"
                f"<script defer>{mhchem_js}</script>"
                f"<script defer>{mathtex_js}</script>"
            )
        css = (
            await self._resources.fetch_text(stylesheet)
            if stylesheet is not None
            else await self._builtin("markdown/github-markdown-light.css")
            + await self._builtin("markdown/pygments-default.css")
        )
        html = await self._templates.render(
            MARKDOWN_TEMPLATES,
            "markdown.html",
            {"md": rendered, "css": "", "extra": extra},
            immutable=True,
        )
        stylesheet_base = (
            await self._worker.run_sync(self._resource_base_url, stylesheet)
            if stylesheet is not None
            else None
        )
        prepared = await self._worker.run_sync(
            parse_html,
            html,
            base_url=markup_base,
            stylesheets=(PreparedStylesheet(css=css, base_url=stylesheet_base),),
        )
        effective_mode = (
            materialization_policy or self._resources.strategy.materialization_policy
        )
        if effective_mode is ResourceMaterializationPolicy.OFF:
            return prepared
        return await materialize_local_assets(
            prepared,
            resources=self._resources,
            strict=effective_mode is ResourceMaterializationPolicy.STRICT,
        )

    async def prepare_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
        *,
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml:
        template_root = await self._worker.run_sync(
            self._resources.authorize_local,
            template.root,
        )
        effective_mode = (
            materialization_policy or self._resources.strategy.materialization_policy
        )
        if effective_mode is ResourceMaterializationPolicy.OFF:
            staged, assets = dict(variables), ()
        else:
            staged, assets = await stage_template_variables(
                variables,
                template_base=template_root,
                resources=self._resources,
                strict=effective_mode is ResourceMaterializationPolicy.STRICT,
            )
        html = await self._templates.render(
            template_root,
            template.name,
            staged,
        )
        base = await self._worker.run_sync(
            self._path_uri,
            template_root,
            directory=True,
        )
        return await self._worker.run_sync(
            parse_html,
            html,
            base_url=base,
            assets=assets,
        )

    async def render_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
    ) -> str:
        template_root = await self._worker.run_sync(
            self._resources.authorize_local,
            template.root,
        )
        return await self._templates.render(
            template_root,
            template.name,
            variables,
        )


__all__ = ["DefaultHtmlPreparer", "HtmlPreparer"]
