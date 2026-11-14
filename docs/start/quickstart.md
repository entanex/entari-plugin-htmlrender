---
title: 快速开始
description: 使用 Takumi 在 Entari 中完成第一次无浏览器渲染
---

# 快速开始

本页使用 Takumi 渲染静态 Markdown，不需要安装浏览器。HTML、纯文本和 Jinja2 模板也使用同一套接口；需要 JavaScript、网页截图或 Markdown 数学公式时，改用[远程 Playwright](../configuration/remote-playwright.md)。

## 安装

```bash
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"
```

Python 要求为 `>=3.11,<4.0`，并依赖 Entari `>=0.19.4,<0.20.0`。`[takumi]` 安装 `takumi-py>=0.4.0`，不设上限；有匹配 wheel 的平台不需要 Rust 工具链，具体见 [Takumi 平台约束](../configuration/providers/takumi.md#platform-requirements)。只安装基础包不会安装渲染后端；其他可选依赖按需添加。

`0.2.x` 面向 Entari 0.19.x。`0.1.0` 基于 Python 3.10 与 Entari 0.18.x，升级时两项运行时基线都需要同步调整；plugin loader 会加载 `0.2.0` 的 metadata、配置模型与 `HtmlRenderService`，不需要在业务插件中手工构造 runtime。

## Entari 配置

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
```

插件短名是 `htmlrender`。`provider` 等字段直接位于这个映射内，没有额外 wrapper。`probe` 在 Launart preparing 阶段启动并探测 Provider；`warmup` 只启动，若只需要模板到 HTML、资源或 graphics，可令 `provider: null` 且保持 `startup: off`。

第一次调用使用英文示例。需要中文时，请先按 [Takumi 字体配置](../configuration/providers/takumi.md#fonts)添加字体文件及其路径白名单；默认字体不能覆盖所有字符。

## 调用

```python
from entari_plugin_htmlrender import RasterOptions, RenderedImage
from entari_plugin_htmlrender.entari import HtmlRenderService

async def render_help(service: HtmlRenderService) -> RenderedImage:
    return await service.renderer.rasterize_markdown(
        "# Hello, Entari\n\nRendered by htmlrender.",
        raster=RasterOptions(width=720),
    )
```

需要把 preparation 与执行分开时，从同一 service 取得 `HtmlPreparer`，再把返回的中立 `PreparedHtml` 交给 renderer：

```python
from entari_plugin_htmlrender import RasterOptions
from entari_plugin_htmlrender.entari import HtmlRenderService

async def prepare_and_render_help(service: HtmlRenderService):
    prepared = await service.preparation.prepare_markdown("# Hello")
    return await service.renderer.rasterize_prepared(
        prepared,
        raster=RasterOptions(width=720),
    )
```

让 Entari DI 把当前插件作用域内的 `HtmlRenderService` 传给 handler。可复用业务函数最好进一步收窄为 `HtmlPreparer`、`HtmlRenderer` 等 caller contract。返回的 `RenderedImage` 可通过 `bytes(image)` 交给消息层；业务代码不需要解析 runtime 或驱动 service 生命周期。

插件热重载或卸载后，Entari 会替换 plugin-scoped service 并完成 cleanup。不要在模块级变量中缓存旧的 service、renderer 或 capability；这些对象属于一次 plugin lifetime，关闭后不可恢复。

模板与本地资源必须位于 `resources.local_access.allowed_paths` 中。下一步可阅读[渲染内容](../guides/rendering-content.md)、[模板与资源](../guides/templates-and-resources.md)与 [Runtime API](../reference/runtime.md)。

## 需要浏览器能力时

Takumi 不执行 JavaScript，也不提供网页导航或选择器截图。Markdown 数学公式仍依赖浏览器中的 KaTeX；交给 Takumi 会抛出 `UnsupportedDocumentFeatureError`。这些需求请使用[远程 Playwright](../configuration/remote-playwright.md)。

!!! warning "本地 Playwright 弃用计划"

    本地 Playwright 浏览器安装、管理与启动将在不久的将来弃用，后续仅保留 remote support。目前本地模式仍可用，尚未确定移除版本或日期。远程模式仍需安装 `[playwright]` Python 客户端，但 Bot 环境不需要执行 `playwright install`。
