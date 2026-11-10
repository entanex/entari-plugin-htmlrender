---
title: 快速开始
description: 在 Entari 中安装、配置并完成第一次渲染
---

# 快速开始

## 安装

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.2.0,<0.3"
uv run playwright install chromium
```

Python 要求为 `>=3.11,<4.0`，并依赖 Entari `>=0.19.4,<0.20.0`。core 不携带浏览器或 native backend；也可按需选择`takumi`、`pillow`、`skia`、`filehost`、`sentry`、`prometheus` extra。

`0.2.x` 面向 Entari 0.19.x。`0.1.0` 基于 Python 3.10 与 Entari 0.18.x，升级时两项运行时基线都需要同步调整；plugin loader 会加载 `0.2.0` 的 metadata、配置模型与 `HtmlRenderService`，不需要在业务插件中手工构造 runtime。

## Entari 配置

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
```

插件短名是 `htmlrender`。`provider` 等字段直接位于这个映射内，没有额外 wrapper。`probe` 在 Launart preparing 阶段启动并探测 Provider；`warmup` 只启动，若只需要模板到 HTML、资源或 graphics，可令 `provider: null` 且保持 `startup: off`。

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
