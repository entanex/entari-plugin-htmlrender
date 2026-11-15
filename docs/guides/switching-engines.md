---
title: 多引擎与切换
description: 切换 Takumi 和远程 Playwright，并在同一服务中使用 Pillow 与 Skia
icon: lucide/arrow-left-right
---

# 多引擎与切换

HTML 渲染与 Python 绘图分别配置。一个 `HtmlRenderService` 只选择一个 HTML 后端，但可以同时启用 Pillow 和 Skia。

| 渲染任务 | 配置入口 | 如何选择 |
| --- | --- | --- |
| HTML、Markdown、文本、Jinja2 模板 | `provider` / `provider_config` | 修改配置并重载 HTMLRender 插件 |
| `RasterScene` 固定场景 | `graphics.backends` / `graphics.backend` | 使用默认 `GraphicsRenderer`，或逐次选择 Pillow/Skia capability |
| Python 绘图函数 | `graphics.drawings.<name>.backend` | 调用 `drawings.render(name, ...)` 选择已配置的绘图名称 |

## 同时启用 HTML 与绘图引擎

以下安装包含本页涉及的四个后端；只使用部分功能时可以删去不需要的 extra：

```bash
uv add "entari-plugin-htmlrender[takumi,playwright,pillow,skia]>=0.2.0"
```

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    graphics:
      backends: [pillow, skia]
      backend: pillow
```

这份配置让 `HtmlRenderer` 使用 Takumi，默认 `GraphicsRenderer` 使用 Pillow，同时保留 Skia 的场景接口。安装 `[playwright]` 只提供客户端，不会同时创建第二个 HTML 后端。Takumi 中文字体需要[另行配置](../configuration/providers/takumi.md#fonts)。

## 切换 Takumi 与远程 Playwright

### 改为远程 Playwright

替换现有 `plugins.htmlrender` 中的 `provider` 和整个 `provider_config`，保留其他资源、绘图与预算配置。下面只列出需要替换的部分：

```yaml
plugins:
  htmlrender:
    provider: playwright
    provider_config:
      engine: chromium
      connect_ws:
        endpoint: ws://browser:3000/
```

将示例地址换成实际浏览器服务地址。也可使用 `connect_cdp` 连接 Chromium，但不能同时配置 `connect_ws` 与 `connect_cdp`。Bot 环境无需执行 `playwright install`，远程服务的版本和资源传输配置见[远程 Playwright](../configuration/remote-playwright.md)。

Takumi 的 `fonts`、`font_families` 等字段不能留在 Playwright 的 `provider_config` 中；两个后端分别校验自己的配置，未知字段会报错。

### 改回 Takumi

同样替换 `provider` 和 `provider_config`，移除浏览器连接字段：

```yaml
plugins:
  htmlrender:
    provider: takumi
    provider_config:
      max_concurrency: 4
```

如果业务需要中文，恢复相应的字体配置及路径白名单。Takumi 不执行 JavaScript，也不支持本插件的 Markdown 数学公式管线；已有浏览器模板中的外链 CSS、`@import` 与 `@font-face` 需要按 [Takumi 资源输入](../configuration/providers/takumi.md)调整。

### 让配置生效

通过 Entari 的配置重载机制重新加载 `htmlrender`；应用未启用配置监听时，重启应用使新配置生效。只编辑配置文件、修改已取得的 service 属性，或调用 `drawings.reload()`，都不能替代 HTML 后端的配置重载。

重载会创建新的服务和后端。业务处理函数继续通过 DI 获取 `HtmlRenderer`，原有 `rasterize_html()`、`rasterize_markdown()` 等调用不变；不要缓存重载前的 service、renderer 或 capability。启用 `startup: probe` 可以在服务准备阶段检查新后端是否可用。失败与恢复方式见[启动与生命周期](../configuration/lifecycle.md)。

`rasterize_*()` 没有逐次传入 `provider` 的参数，`.capabilities.takumi` 与 `.capabilities.playwright` 也不会因为安装了两个 extra 就同时可用。需要并行持有两个 HTML 后端的独立应用，应分别创建并关闭两个运行时，见[手动组装运行时](../reference/runtime.md)。

> [!NOTE]
> 本插件将在不久的将来弃用 Playwright 本地浏览器安装、管理与启动，仅保留远程连接。当前本地模式仍可用，尚未指定移除版本或日期。

## 逐次选择 Pillow 或 Skia 场景渲染

在 `graphics.backends` 中同时启用两个后端后，可以把同一个 `RasterScene` 交给不同实现：

```python
from entari_plugin_htmlrender import RenderedImage
from entari_plugin_htmlrender.entari import HtmlRenderService
from entari_plugin_htmlrender.graphics import RasterScene

async def render_both(
    service: HtmlRenderService,
    scene: RasterScene,
) -> tuple[RenderedImage, RenderedImage]:
    pillow_image = await service.capabilities.pillow.rasterize(scene)
    skia_image = await service.capabilities.skia.rasterize(scene)
    return pillow_image, skia_image
```

`service.graphics` 和直接注入的 `GraphicsRenderer` 使用配置的默认后端。省略 `graphics.backend` 时使用 `backends` 的第一项；显式设置时，该后端必须出现在列表中。修改默认后端需要配置重载，逐次选择 capability 则不需要。两个实现不保证逐像素或编码字节一致，场景模型见[绘制 RasterScene](raster-scenes.md)。

## 按名称切换 Python 绘图

Python 绘图函数绑定配置中的后端。需要两种实现时，为它们配置两个名称，而不是把同一个后端专用函数交给另一种画布。下面使用仓库中的现成示例文件；部署时换成自己的文件路径：

```yaml
plugins:
  htmlrender:
    provider: takumi
    graphics:
      backends: [pillow, skia]
      drawings:
        card-pillow:
          backend: pillow
          path: examples/graphics_render/pillow_card.py
        card-skia:
          backend: skia
          path: examples/graphics_render/skia_card.py
```

```python
from typing import Literal

from entari_plugin_htmlrender import RenderedImage
from entari_plugin_htmlrender.graphics import DrawingRenderer, RGBAColor

async def render_card(
    drawings: DrawingRenderer,
    engine: Literal["pillow", "skia"],
) -> RenderedImage:
    names = {"pillow": "card-pillow", "skia": "card-skia"}
    return await drawings.render(
        names[engine],
        {"title": "Hello, Entari", "subtitle": "Python drawing"},
        width=640,
        height=360,
        background=RGBAColor(15, 23, 42),
    )
```

两个绘图都已配置时，选择名称不会重载插件；每次调用都会创建新的画布。新增名称、改变绑定后端或修改路径属于配置变更，需要重新加载插件。只修改绘图函数源码时，可用 `reload: true` 或 `await drawings.reload(name)`，具体步骤见 [Python 绘图](python-drawing.md)。

只需要 Pillow/Skia 时，可以使用 `provider: null`、`startup: off`，保留 `graphics` 配置；无需启动 HTML 后端。

## 后端不可用时

插件不会自动改用另一种引擎。先确认对应 extra、原生依赖和配置均有效。读取未启用的 capability 会得到 `CapabilityUnavailableError`，缺少绘图后端会得到 `GraphicsBackendUnavailableError`。渲染方式不同的业务应在调用前显式选择，不要把失败结果当成可以无条件重试到另一个后端的信号。
