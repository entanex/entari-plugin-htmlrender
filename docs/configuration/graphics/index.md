---
title: Graphics 后端
description: Pillow 与 Skia 共享的 RasterScene 契约和预算
---

# Graphics 后端

Graphics 后端提供进程内 `RasterScene` 渲染。它们不消费 `PreparedHtml`，也不是`EngineProvider`；是否启用与 `provider` 相互独立。

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
      backends: [pillow, skia]
      max_pixels: 16777216
      max_concurrency: 2
      max_commands: 100000
```

| 键 | 默认值 |
| --- | ---: |
| `graphics.backends` | `[]` |
| `graphics.max_pixels` | `16777216` |
| `graphics.max_concurrency` | `2` |
| `graphics.max_commands` | `100000` |

后端共享像素、命令与并发预算，不能通过切换实现绕过限制。调用方显式选择`runtime.extensions.pillow` 或 `.skia`；不存在自动回退。
