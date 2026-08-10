---
title: 术语表
description: htmlrender 当前架构中的稳定术语
---

# 术语表

| 术语 | 定义 |
| --- | --- |
| `RenderRuntime` | 一次 composition 的 host-neutral 聚合根，拥有 renderer、preparation、resources、extensions 与 lifecycle |
| `HtmlRenderer` | 执行 typed、跨 HTML Provider request 的 facade |
| `RuntimeResolver` | 同步返回已组合 `RenderRuntime` 的结构化协议；不得执行 I/O 或 startup |
| `RuntimeSource` | `RenderRuntime \| RuntimeResolver` |
| `HtmlRenderService` | Entari/Launart 拥有的 service，同时实现 `RuntimeResolver` |
| `PreparedHtml` | markup 解析后的不可变中立文档，包含 base、structure、stylesheets、assets 与 requirements |
| Provider | 发现、解析专属配置并组合一个 HTML executor/lifecycle 的扩展 |
| Capability | 无法放入通用 HTML 契约的 typed 专属能力 |
| `RasterScene` | Pillow/Skia 消费的物理像素场景；不表示 HTML 布局 |
| admission gate | cleanup 开始后拒绝新操作，并等待已获准操作完成的 runtime 门禁 |
| `ResourceResolution[T]` | 解析值与每个精确 URL 授权 header 的组合结果 |
| artifact | 渲染结果值，例如 `RenderedImage` 或 `RenderedHtml` |

配置中的 `provider` 选择 Playwright、Takumi 或第三方 HTML Provider；`graphics.backends` 独立启用 Pillow/Skia。
