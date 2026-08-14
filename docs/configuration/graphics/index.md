---
title: Graphics 后端
description: Pillow 与 Skia 共享的 RasterScene contract 和预算
---

# Graphics 后端

Graphics 后端提供进程内 `RasterScene` 渲染。它们不消费 `PreparedHtml`，也不是`RenderProvider`；是否启用与 `provider` 相互独立。

| 后端 | 适用场景 |
| --- | --- |
| [Pillow](pillow.md) | 兼容面优先的普通 CPU 位图输出 |
| [Skia](skia.md) | 已部署 Skia native runtime 的环境 |

## Graphics settings

```yaml
plugins:
  htmlrender:
    provider: null
    graphics:
      backend: pillow
      max_pixels: 16777216
      max_concurrency: 2
      max_commands: 100000
```

| 键 | 默认值 |
| --- | ---: |
| `graphics.backend` | `null` |
| `graphics.max_pixels` | `16777216` |
| `graphics.max_concurrency` | `2` |
| `graphics.max_commands` | `100000` |

一次 composition 选择零个或一个 backend。调用方始终使用`HtmlRenderService.graphics` / `GraphicsRenderer`；没有按实现分支，也不会自动回退。像素、命令与并发预算位于 adapter 外层，不能通过切换 backend 绕过限制。

## 下一步

选定后端后打开对应配置页，并用[绘制 RasterScene](../../guides/raster-scenes.md)验证部署。需要 HTML、Markdown、文本或模板渲染时，应选择独立的 [HTML Provider](../providers/index.md)。
