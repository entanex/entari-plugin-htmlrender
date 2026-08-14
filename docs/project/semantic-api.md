---
title: 语义 API 设计
description: caller-first 调用面、领域词汇、失败语义与模块边界
---

# 语义 API 设计

当前 API 将普通调用收口为显式注入的领域契约，每个入口都固定输入身份、动作与输出 artifact。

## 调用方先行

### Entari 中渲染 Markdown

```python
from entari_plugin_htmlrender import RasterOptions, RenderedImage
from entari_plugin_htmlrender.entari import HtmlRenderService

async def render_help(service: HtmlRenderService) -> RenderedImage:
    return await service.renderer.rasterize_markdown(
        "# Hello, Entari",
        raster=RasterOptions(width=720),
    )
```

业务函数可以只依赖中立契约，不依赖 Entari 或 runtime 容器：

```python
from entari_plugin_htmlrender import HtmlRenderer, RenderedImage

async def render_badge(renderer: HtmlRenderer, html: str) -> RenderedImage:
    return await renderer.rasterize_html(html)
```

### 模板的 HTML 与图片输出

```python
from pathlib import Path

from entari_plugin_htmlrender import RasterOptions, TemplateRef
from entari_plugin_htmlrender.entari import HtmlRenderService

CARD = TemplateRef(Path("templates"), "card.html")

async def render_card(service: HtmlRenderService, name: str):
    variables = {"name": name}
    html = await service.templates.render(CARD, variables)
    image = await service.renderer.rasterize_template(
        CARD,
        variables,
        raster=RasterOptions(width=440),
    )
    return html, image
```

### 资源载荷与发布身份

```python
from pathlib import Path

from entari_plugin_htmlrender.entari import HtmlRenderService
from entari_plugin_htmlrender.resources import FileResourceRef

async def send_logo(service: HtmlRenderService):
    content = await service.resources.fetch(FileResourceRef(Path("logo.png")))
    async with service.resources.publish(content, suffix=".png") as published:
        return await send_to_consumer(
            published.url,
            request_headers=published.request_headers,
        )
```

`PublishedResource` 原子携带 URL 与该精确 URL 所需的请求头。调用方不再从 side-table 单独取出 URL，因而不会静默丢失授权。其身份只在 `publish()` 的 async context 内有效，不能在 lease 退出后缓存或返回 URL。

### 可选能力与 Graphics

```python
from entari_plugin_htmlrender.entari import HtmlRenderService
from entari_plugin_htmlrender.graphics import RasterScene

async def rasterize_scene(service: HtmlRenderService, scene: RasterScene):
    image = await service.graphics.rasterize(scene)
    async with service.capabilities.playwright.lease_page() as page:
        await page.set_content("<strong>ready</strong>")
    return image
```

Graphics backend 只在配置与 composition 中选择；业务调用不分支 Pillow/Skia。切换 HTML Provider 同样不改变上述调用。

## 领域词汇

| 词 | 固定语义 |
| --- | --- |
| `parse` | 纯同步 markup → `PreparedHtml` |
| `prepare` | 可能执行 I/O 的 source → `PreparedHtml` |
| `render` | 模板 → `RenderedHtml` |
| `rasterize` | HTML、文本、Markdown、模板、prepared document 或 `RasterScene` → `RenderedImage` |
| `fetch` | 从 `ResourceRef` 取得 `ResourceContent`，可能执行文件或网络 I/O |
| `publish` | 在一个显式 lease 内把内容变成 `PublishedResource` |
| `resolve` | 从 ID、handle 或引用得到确定身份；同步解析不得隐藏 I/O |
| `provider` | 配置选择的 HTML raster 实现 |
| `capability` | 可选且类型化的动作集合 |
| `lease` | 只在 async context 内有效的 native access |
| `service` | Entari/Launart 拥有生命周期的 host component |

## 公开契约

- `HtmlRenderer` 只公开 output-explicit 的 `rasterize_*` 方法。
- `TemplateRenderer` 只负责模板到 `RenderedHtml`。
- `ResourceAccess` 使用 `ResourceRef`、`ResourceContent` 与 `PublishedResource` 分离定位、载荷与发布身份。
- `GraphicsRenderer` 隐藏 Pillow/Skia selection。
- `HtmlRenderService` 是显式 concrete Entari service；中立调用契约不包含 `startup()`、`probe()` 或 `aclose()`。
- `RenderRuntime`、composition plan、bindings、admission gate、catalog、observer 与 discovery 都是 advanced/composition API，不进入根导出。

## 失败语义

| 情况 | 稳定错误 | 结构化恢复字段 |
| --- | --- | --- |
| 输入无效 | `InvalidRenderInputError` | `operation`、`field` |
| 当前实现不支持动作 | `UnsupportedOperationError` | `operation`、`provider_id` |
| 操作超过 deadline | `RenderTimeoutError` | `operation`、`timeout_seconds` |
| 输出超过安全预算 | `RenderOutputLimitError` | `operation`、`limit`、`actual`、`maximum` |
| runtime 已关闭或不可用 | `RuntimeUnavailableError` | `state` |
| Provider 未发现或配置错误 | `ProviderSelectionError` 子类 | `provider_id` |
| Provider 环境不可用 | `ProviderUnavailableError` | `provider_id`、`reason`、`retryable` |
| Provider 执行或生命周期失败 | `ProviderError` 子类 | `provider_id`、`operation`、`retryable` |
| 资源不存在、拒绝、过大、fetch 或 publish 失败 | `ResourceError` 子类 | `reference`、`operation`、`retryable` |
| 可选 capability 未配置 | `CapabilityUnavailableError` | `capability` |

`ErrorCause` 只保存有界诊断信息，不替代这些恢复字段。`None` 只表示正常缺失，不吞掉不支持、权限、网络或生命周期失败。

## 模块方向

```text
rendering/resources/graphics values + contracts + errors
                           ↑
              application use cases
                           ↑
          providers + concrete adapters
                           ↑
              framework-neutral composition
                           ↑
                 Entari service/registration
```

根包只导出普通调用所需的 contract、常用 value object、artifact 与根错误。Provider author API 位于 `providers`，资源高级 API 位于 `resources`，Entari 类型位于 `entari`。任何核心模块都不得反向 import adapter、composition 或 Entari。
