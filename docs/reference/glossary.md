---
title: 术语表
description: htmlrender 的唯一领域词汇
---

# 术语表

| 术语 | 固定定义 |
| --- | --- |
| parse | 纯同步 markup → `PreparedHtml` |
| prepare | 可能执行 I/O 的 source → `PreparedHtml` application step |
| render | `TemplateRef` → `RenderedHtml` |
| rasterize | HTML、文本、Markdown、模板、prepared document 或 `RasterScene` → `RenderedImage` |
| fetch | 从 `ResourceRef` 取得 `ResourceContent`，可能执行文件或网络 I/O |
| publish | 在显式 lease 内把 payload 变成 `PublishedResource` |
| resolve | 从 ID/handle/ref 得到确定身份；不表示 fetch 或 publish |
| Provider | 发现、解析专属配置并组合 HTML executor/lifecycle 的实现 |
| Capability | 无法放入通用 caller contract 的可选 typed 动作集合 |
| lease | 只在 async context 内有效的 native access |
| `HtmlRenderer` | 将 caller 内容 rasterize 为 `RenderedImage` 的中立 contract |
| `TemplateRenderer` | 将 `TemplateRef` render 为 `RenderedHtml` 的中立 contract |
| `ResourceAccess` | caller-facing fetch 与 scoped publish contract |
| `GraphicsRenderer` | 将 `RasterScene` rasterize 为图片并隐藏 backend selection 的 contract |
| `HtmlRenderService` | Entari/Launart 拥有生命周期的 concrete service |
| `RenderRuntime` | advanced composition aggregate；普通业务代码不依赖它 |
| `PreparedHtml` | parse 后的不可变中立文档，包含 base、structure、stylesheets、assets 与 requirements |
| `PublishedResource` | publication lease 内有效的 URL 与精确请求头原子值 |
| artifact | 操作结果值，例如 `RenderedImage` 或 `RenderedHtml` |

配置中的 `provider` 选择 Playwright、Takumi 或第三方 HTML Provider；`graphics.backend` 独立选择 Pillow/Skia。代码与文档统一使用本表词汇。
