---
title: 渲染 API
description: HtmlRenderer、TemplateRenderer、artifact 与稳定错误
---

# 渲染 API

## HtmlRenderer

`HtmlRenderer` 是普通图片渲染调用的唯一 contract。输入类型与输出 artifact 都写在方法名和签名中，不需要 request DTO：

| 方法 | 输入 | 输出 |
| --- | --- | --- |
| `rasterize_html()` | inline HTML | `RenderedImage` |
| `rasterize_text()` | inline text | `RenderedImage` |
| `rasterize_markdown()` | inline `str` 或显式 `ResourceRef` | `RenderedImage` |
| `rasterize_template()` | `TemplateRef` + variables | `RenderedImage` |
| `rasterize_prepared()` | `PreparedHtml` | `RenderedImage` |

```python
from entari_plugin_htmlrender import (
    HtmlRenderer,
    RasterOptions,
    RenderedImage,
)

async def render_readme(
    renderer: HtmlRenderer,
    source: str,
) -> RenderedImage:
    return await renderer.rasterize_markdown(
        source,
        raster=RasterOptions(width=720, format="png"),
    )
```

`rasterize_html()`、`rasterize_text()`、`rasterize_markdown()` 与 `rasterize_template()` 完整拥有 convenience preparation。需要检查、缓存或分步传递中立文档时，先使用 `service.preparation`，再调用：

```python
from entari_plugin_htmlrender import HtmlPreparer, HtmlRenderer, RasterOptions

async def render_prepared(
    preparation: HtmlPreparer,
    renderer: HtmlRenderer,
):
    prepared = await preparation.prepare_markdown("# Prepared once")
    return await renderer.rasterize_prepared(
        prepared,
        raster=RasterOptions(width=720),
    )
```

所有方法的 `raster`、`materialization_policy` 与 `timeout_seconds` 都是 kw-only。Markdown `str` 永远是 inline 内容；文件、包或远端文档必须传入对应 `ResourceRef`，不会按字符串形状猜测来源。

`supported_operations` 返回 `frozenset[RenderOperation]`，`supports(operation)`用于探测当前 composition。`RenderOperation` 同时描述输入领域与输出 artifact，例如`HTML_TO_IMAGE`、`TEMPLATE_TO_HTML` 与 `RASTER_SCENE_TO_IMAGE`；它不是 Python
method name。

## TemplateRenderer

`TemplateRenderer.render()` 只负责 `TemplateRef` 到 `RenderedHtml`：

```python
from pathlib import Path

from entari_plugin_htmlrender import RenderedHtml, TemplateRef, TemplateRenderer

async def render_email(templates: TemplateRenderer) -> RenderedHtml:
    return await templates.render(
        TemplateRef(Path("templates"), "email.html"),
        {"title": "ready"},
    )
```

模板调用支持可选的 `filters: Mapping[str, FilterCallable]` 与 `extensions: Sequence[ExtensionSpec]`；前者按名称注入 callable，后者接受导入路径或 Jinja Extension 类。两项在挂起前复制为快照，避免并发调用修改同一个配置对象。完整示例见[模板与资源](../guides/templates-and-resources.md#template-customization)。

需要图片时调用 `HtmlRenderer.rasterize_template()`；不要把 template-to-HTML 与template-to-image 合并成一个按参数改变返回类型的方法。

`service.preparation.render_template()` 返回同一 preparation pipeline 产生的原始 HTML `str`，供需要组合内部阶段的高级调用方使用；普通业务代码优先使用 `TemplateRenderer.render()` 获得 `RenderedHtml` artifact。

## Artifact

`RenderedImage` 的 `data`、`format`、`width`、`height` 来自编码数据的有界检查；`bytes(image)` 显式取得 payload，`image.media_type` 返回对应媒体类型。`RenderedHtml.content` 保存模板输出，`str(html)` 显式取得字符串。`RasterImageFormat` 目前固定为 `"png" | "jpeg"`，由 `RasterOptions.format` 与`RenderedImage.format` 共享。

## 错误

所有稳定失败继承 `HtmlRenderError`。根包导出普通调用最常用的错误根；需要按具体Provider 或资源失败恢复时，从领域模块导入：

```python
from entari_plugin_htmlrender import (
    HtmlRenderError,
    InvalidRenderInputError,
    RenderOutputLimitError,
    RenderTimeoutError,
)
from entari_plugin_htmlrender.errors import ProviderExecutionError
from entari_plugin_htmlrender.resources import ResourceNotFoundError
```

| 失败 | 结构化字段 |
| --- | --- |
| `InvalidRenderInputError` | `operation`、`field` |
| `UnsupportedOperationError` | `operation`、`provider_id` |
| `RenderTimeoutError` | `operation`、`timeout_seconds` |
| `RenderOutputLimitError` | `operation`、`limit`、`actual`、`maximum` |
| `RuntimeUnavailableError` | `state`、`operation` |
| `ProviderError` 子类 | `provider_id`、`operation`、`retryable` |
| `ResourceError` 子类 | `reference`、`operation`、`retryable` |
| `CapabilityUnavailableError` | `capability` |

`entari_plugin_htmlrender.errors.ErrorCause` 是经过裁剪的底层诊断快照，不替代上述恢复字段。业务代码应匹配稳定类型与字段，不解析异常文本。
