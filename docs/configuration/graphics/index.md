---
title: 绘图后端
description: 使用 Pillow 或 Skia 绘制固定场景和 Python 卡片
icon: lucide/palette
---

# 绘图后端

Pillow 与 Skia 都支持两条独立路径：

| 需要的能力 | 使用入口 | 适合的内容 |
| --- | --- | --- |
| 固定的纯色矩形场景 | `service.graphics` / `GraphicsRenderer` | 可序列化、命令数量受限的场景 |
| 直接使用 Pillow 或 Skia 提供的接口 | `service.drawings` / `DrawingRenderer` | Python 代码生成的卡片、图表和装饰图 |

`RasterScene` 是可序列化的固定场景，由 `GraphicsRenderer.rasterize()` 执行。Python 绘图按配置名称加载可信源码，由 `DrawingRenderer.render()` 执行，每次返回编码后的 `RenderedImage`。两种用法使用相同的 `graphics.max_pixels` 上限；`graphics.max_concurrency` 在每个后端内共享，Pillow 与 Skia 分别计数；`graphics.max_commands` 只限制 `RasterScene.commands`，无法统计 Python 回调中的 native 绘图调用。

分步骤安装、编写回调、调用 `DrawingRenderer`、取得字节和处理源码重载的完整流程见[Python 绘图](../../guides/python-drawing.md)。本文保留后端选择、配置字段和固定场景入口的参考信息。

## 配置

下面的配置同时启用 Pillow 与 Skia，并注册三个命名绘图：

```yaml
basic:
  external_dirs:
    - examples/graphics_render

plugins:
  htmlrender:
    provider: null
    graphics:
      backends: [pillow, skia]
      max_pixels: 16777216
      max_concurrency: 2
      max_commands: 100000
      drawings:
        profile:
          backend: pillow
          path: examples/graphics_render/shared_cards/profile.py
          reload: true
        badge:
          backend: pillow
          module: shared_cards.badge
          reload: false
        skia-profile:
          backend: skia
          path: examples/graphics_render/skia_card.py
```

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `graphics.backend` | `null` | 兼容的单选后端 |
| `graphics.backends` | `[]` | 显式启用的完整后端列表 |
| `graphics.drawings` | `{}` | 名称到 Python 绘图配置的映射 |
| `graphics.drawings.<name>.backend` | 必填 | `pillow` 或 `skia` |
| `graphics.drawings.<name>.path` | `null` | `.py` 文件路径 |
| `graphics.drawings.<name>.module` | `null` | 可导入的 Python 模块名 |
| `graphics.drawings.<name>.function` | `draw` | 模块中的绘图函数名 |
| `graphics.drawings.<name>.reload` | `false` | 下一次渲染前主动检查源码变化 |
| `graphics.max_pixels` | `16777216` | 单个场景或画布的像素上限 |
| `graphics.max_concurrency` | `2` | 每个后端内场景与 Python 绘图共用的并发上限；后端之间独立计数 |
| `graphics.max_commands` | `100000` | 单个 `RasterScene` 的命令上限 |

每项绘图必须设置 `backend`，并在 `path` 与 `module` 中恰好选择一个。配置引用的后端会自动启用，不必重复加入 `backends`，但仍需安装对应依赖：

```bash
uv add "entari-plugin-htmlrender[pillow,skia]>=0.2.0"
```

相对 `path` 按进程工作目录解析。`module` 与 `path` 都应解析到正常的 Python 源码；带 `__init__.py` 的包可以把绘图函数直接写在包入口，此时 `module` 使用包名。共享模块、初始入口包、重载限制和独立运行时差异集中记录在 [Python 绘图指南](../../guides/python-drawing.md)。

`reload: false` 只关闭逐次源码检查；显式 `await drawings.reload(name)` 仍会刷新入口。新增绘图或改变后端、路径与函数配置需要重载 HTMLRender 插件。

## 后端选择

`graphics.backend` 是兼容的单选字段，`graphics.backends` 是显式列表。只配置绘图时，第一个绘图引用的后端也会成为固定场景的默认后端：

| 配置 | 启用的后端 | `service.graphics` |
| --- | --- | --- |
| `backend`、`backends` 都省略 | 无 | 调用时提示补充配置 |
| 只设置 `backend` | 该项 | 该项 |
| 只设置 `backends` | 列表全部项 | 第一项 |
| `backend`、`backends` 都设置 | `backends` 全部项 | `backend` |

`backend` 与 `backends` 同时出现时，`backend` 必须包含在 `backends` 中。成功启用的后端还会提供 `runtime.capabilities.pillow` 或 `runtime.capabilities.skia`。Pillow 与 Skia 是 Graphics 后端，不进入 HTML 的 `provider` 选择；独立后端安装和平台差异见 [Pillow](pillow.md) 与 [Skia](skia.md)。同一服务中切换 HTML Provider、场景 capability 与绘图名称的配置和调用差异见[多引擎与切换](../../guides/switching-engines.md)。

## 固定场景

固定场景使用 backend-neutral 的 `RasterScene`：

```python
from entari_plugin_htmlrender.graphics import (
    FillRect,
    GraphicsRenderer,
    PixelRect,
    RasterScene,
    RGBAColor,
)

async def render_scene(graphics: GraphicsRenderer):
    return await graphics.rasterize(
        RasterScene(
            320,
            180,
            background=RGBAColor(15, 23, 42),
            commands=(FillRect(PixelRect(24, 24, 272, 132), RGBAColor(30, 41, 59)),),
        )
    )
```

`RasterScene` 目前只支持按顺序执行的纯色整数像素矩形，不提供 HTML 布局、文本整形或 Pillow/Skia native 对象。完整调用和预算说明见[绘制 RasterScene](../../guides/raster-scenes.md)。如果内容需要文本、路径、圆角或直接调用 native API，应使用 `DrawingRenderer`。

绘图文件按可信本地 Python 代码执行，没有沙箱。不要让消息或其他不可信输入决定 `path`、`module` 或 `function`；并发绘图需要自行保证共享状态可安全使用。HTML、Markdown、文本和模板渲染使用独立的[网页渲染后端](../providers/index.md)。
