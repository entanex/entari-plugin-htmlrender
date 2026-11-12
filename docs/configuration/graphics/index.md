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
      backends: [pillow, skia]
      max_pixels: 16777216
      max_concurrency: 2
      max_commands: 100000
```

| 键 | 默认值 |
| --- | ---: |
| `graphics.backend` | `null` |
| `graphics.backends` | `[]` |
| `graphics.drawings` | `{}` |
| `graphics.max_pixels` | `16777216` |
| `graphics.max_concurrency` | `2` |
| `graphics.max_commands` | `100000` |

`graphics.backends` 是本次 composition 启用的完整集合；顺序保留，且不允许重复。它的第一项在没有显式 `graphics.backend` 时成为 `HtmlRenderService.graphics` 的默认实现，因此只写 `backends: [pillow, skia]` 就能同时获得 Pillow/Skia 能力并保持 Pillow 为主入口。

`graphics.backend` 是兼容的单选入口：

| 配置 | 可用 backend | `service.graphics` |
| --- | --- | --- |
| 两者都省略 | 无 | 不可用 renderer，首次调用给出配置诊断 |
| 只设置 `backend` | 该项 | 该项 |
| 只设置 `backends` | 列表全部项 | 第一项 |
| 两者都设置 | `backends` 全部项 | `backend` |

两者同时出现时，`backend` 必须包含在 `backends` 中，否则配置校验失败。每个成功加载的 backend 都进入独立的 typed capability：`runtime.capabilities.pillow` 或 `runtime.capabilities.skia`。

所有 backend 共享同一个 runtime admission、worker 与 operation observer，并各自拥有独立的 `RasterWorkBudget`。每个 backend 均独立执行像素、命令和并发限制；同时启用两个 backend 时，总并发上限为各 backend 上限之和。缺少 extra 时不会自动回退到另一实现。

## 下一步

选定后端后打开对应配置页，并用[绘制 RasterScene](../../guides/raster-scenes.md)验证部署。需要 HTML、Markdown、文本或模板渲染时，应选择独立的 [HTML Provider](../providers/index.md)。
