from __future__ import annotations

from collections.abc import (  # noqa: TC003 -- runtime public annotations
    Mapping,
    Sequence,
)
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, final, runtime_checkable

from entari_plugin_htmlrender.resources.config import ResourceMaterializationPolicy
from entari_plugin_htmlrender.resources.models import (
    FileResourceRef,
    PackageResourceRef,
    RemoteResourceRef,
    ResourceRef,
)
from entari_plugin_htmlrender.resources.source import PackageResourceSource
from entari_plugin_htmlrender.resources.templating import (  # noqa: TC001 -- public hints
    ExtensionSpec,
    FilterCallable,
)

from .html import parse_html
from .markdown_render import render_markdown
from .materialize import materialize_local_assets
from .models import PreparedHtml, PreparedStylesheet, TemplateRef
from .template_assets import stage_template_variables

if TYPE_CHECKING:
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


@runtime_checkable
class HtmlPreparer(Protocol):
    """Prepare reusable HTML documents independently of a rendering provider."""

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
        filters: Mapping[str, FilterCallable] | None = None,
        extensions: Sequence[ExtensionSpec] = (),
        materialization_policy: ResourceMaterializationPolicy | None = None,
    ) -> PreparedHtml: ...

    async def render_template(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
        *,
        filters: Mapping[str, FilterCallable] | None = None,
        extensions: Sequence[ExtensionSpec] = (),
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
        markdown_render = await self._worker.run_sync(
            render_markdown,
            markdown_text,
        )
        extra = ""
        if markdown_render.has_math:
            katex_css = await self._builtin("markdown/katex/katex.min.b64_fonts.css")
            katex_js = await self._builtin("markdown/katex/katex.min.js")
            mhchem_js = await self._builtin("markdown/katex/mhchem.min.js")
            arithmatex_js = await self._builtin("markdown/katex/arithmatex.js")
            extra = (
                f'<style type="text/css">{katex_css}</style>'
                f'<script defer data-htmlrender-math-runtime="katex">{katex_js}</script>'
                f'<script defer data-htmlrender-math-runtime="mhchem">{mhchem_js}</script>'
                f'<script defer data-htmlrender-math-runtime="arithmatex">'
                f"{arithmatex_js}</script>"
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
            {"md": markdown_render.html, "css": "", "extra": extra},
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
        filters: Mapping[str, FilterCallable] | None = None,
        extensions: Sequence[ExtensionSpec] = (),
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
            filters=filters,
            extensions=extensions,
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
        *,
        filters: Mapping[str, FilterCallable] | None = None,
        extensions: Sequence[ExtensionSpec] = (),
    ) -> str:
        template_root = await self._worker.run_sync(
            self._resources.authorize_local,
            template.root,
        )
        return await self._templates.render(
            template_root,
            template.name,
            variables,
            filters=filters,
            extensions=extensions,
        )


__all__ = ["DefaultHtmlPreparer", "HtmlPreparer"]
