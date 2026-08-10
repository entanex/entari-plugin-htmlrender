"""Private application use cases composed behind the public renderer contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from entari_plugin_htmlrender.rendering.artifacts import RenderedHtml, RenderedImage
from entari_plugin_htmlrender.rendering.models import RenderOperation

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.preparation.models import (
        PreparedHtml,
        RasterOptions,
        TemplateRef,
    )
    from entari_plugin_htmlrender.preparation.service import HtmlPreparer
    from entari_plugin_htmlrender.rendering.ports import PreparedHtmlExecutor
    from entari_plugin_htmlrender.resources.config import (
        ResourceMaterializationPolicy,
    )
    from entari_plugin_htmlrender.resources.models import ResourceRef


@final
class _RasterizeHtml:
    def __init__(
        self,
        *,
        preparer: HtmlPreparer,
        executor: PreparedHtmlExecutor,
    ) -> None:
        self._preparer = preparer
        self._executor = executor

    async def execute(
        self,
        html: str,
        *,
        raster: RasterOptions,
        base_url: str | None,
        materialization_policy: ResourceMaterializationPolicy | None,
    ) -> RenderedImage:
        prepared = await self._preparer.prepare_html(html, base_url=base_url)
        return await self._executor.execute(
            prepared,
            raster,
            operation=RenderOperation.HTML_TO_IMAGE,
            materialization_policy=materialization_policy,
        )


@final
class _RasterizeText:
    def __init__(
        self,
        *,
        preparer: HtmlPreparer,
        executor: PreparedHtmlExecutor,
    ) -> None:
        self._preparer = preparer
        self._executor = executor

    async def execute(
        self,
        text: str,
        *,
        stylesheet: ResourceRef | None,
        raster: RasterOptions,
        materialization_policy: ResourceMaterializationPolicy | None,
    ) -> RenderedImage:
        prepared = await self._preparer.prepare_text(
            text,
            stylesheet=stylesheet,
        )
        return await self._executor.execute(
            prepared,
            raster,
            operation=RenderOperation.TEXT_TO_IMAGE,
            materialization_policy=materialization_policy,
        )


@final
class _RasterizeMarkdown:
    def __init__(
        self,
        *,
        preparer: HtmlPreparer,
        executor: PreparedHtmlExecutor,
    ) -> None:
        self._preparer = preparer
        self._executor = executor

    async def execute(
        self,
        source: str | ResourceRef,
        *,
        stylesheet: ResourceRef | None,
        raster: RasterOptions,
        materialization_policy: ResourceMaterializationPolicy | None,
    ) -> RenderedImage:
        prepared = await self._preparer.prepare_markdown(
            source,
            stylesheet=stylesheet,
            materialization_policy=materialization_policy,
        )
        return await self._executor.execute(
            prepared,
            raster,
            operation=RenderOperation.MARKDOWN_TO_IMAGE,
            materialization_policy=materialization_policy,
        )


@final
class _RasterizeTemplate:
    def __init__(
        self,
        *,
        preparer: HtmlPreparer,
        executor: PreparedHtmlExecutor,
    ) -> None:
        self._preparer = preparer
        self._executor = executor

    async def execute(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
        *,
        raster: RasterOptions,
        materialization_policy: ResourceMaterializationPolicy | None,
    ) -> RenderedImage:
        prepared = await self._preparer.prepare_template(
            template,
            variables,
            materialization_policy=materialization_policy,
        )
        return await self._executor.execute(
            prepared,
            raster,
            operation=RenderOperation.TEMPLATE_TO_IMAGE,
            materialization_policy=materialization_policy,
        )


@final
class _RasterizePrepared:
    def __init__(self, *, executor: PreparedHtmlExecutor) -> None:
        self._executor = executor

    async def execute(
        self,
        prepared: PreparedHtml,
        *,
        raster: RasterOptions,
        materialization_policy: ResourceMaterializationPolicy | None,
    ) -> RenderedImage:
        return await self._executor.execute(
            prepared,
            raster,
            operation=RenderOperation.PREPARED_HTML_TO_IMAGE,
            materialization_policy=materialization_policy,
        )


@final
class _RenderTemplate:
    def __init__(self, *, preparer: HtmlPreparer) -> None:
        self._preparer = preparer

    async def execute(
        self,
        template: TemplateRef,
        variables: Mapping[str, object],
    ) -> RenderedHtml:
        content = await self._preparer.render_template(template, variables)
        return RenderedHtml(content=content)


__all__: list[str] = []
