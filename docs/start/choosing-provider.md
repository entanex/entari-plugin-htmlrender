---
title: 选择 Provider
description: Playwright、Takumi 与 Graphics backend 的选择边界
---

# 选择 Provider

`provider` 只选择 HTML raster Provider；Pillow/Skia 实现独立的 `GraphicsRenderer`，不参与 Provider 选择。

| 实现 | 适用需求 | 主要代价 |
| --- | --- | --- |
| Playwright | 浏览器布局、JavaScript、导航、selector 截图 | 浏览器进程或兼容远程 endpoint |
| Takumi | 无浏览器静态 HTML、SVG、动态字体 | 依赖受支持平台的 native wheel |
| Pillow | 物理像素矩形场景，不需要 HTML 布局 | Python image stack，能力面刻意较小 |
| Skia | 同一 `RasterScene` 的 Skia 实现 | wheel 与系统图形库的平台约束 |

Markdown 数学走 `pymdownx.arithmatex` 的 generic 标记管线。需要让包内 KaTeX 初始化脚本仅针对带 `data-htmlrender-arithmatex` 的生成容器完成排版时选择 Playwright。含公式的 preparation 可以成功，但它会设置 `DocumentRequirement.JAVASCRIPT`，Takumi rasterization 会以 `UnsupportedDocumentFeatureError` 拒绝；若静态 Provider 必须输出可见公式，应先把公式转换为无需客户端脚本的静态 HTML/SVG。

Pillow 与 Skia 可在 `graphics.backends` 中同时启用。首项作为 `service.graphics` 默认 renderer，也可用兼容字段 `graphics.backend` 指定主入口；两者同时配置时，`backend` 必须出现在 `backends` 中。启用后可分别通过 `service.capabilities.pillow` 与 `service.capabilities.skia` 选择实现。

首次接入通用 HTML rasterization 优先 Playwright；生产环境通常把浏览器放在独立容器并通过 CDP/WS 连接。只有确认内容不依赖浏览器语义时才切换 Takumi。业务只依赖 `HtmlRenderer` 时，Provider 切换不改变 convenience calls 或 `rasterize_prepared()` 的调用形态。

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    graphics:
      backend: pillow
```

选择 extra 只安装 Python distribution；远程服务版本、浏览器二进制、native wheel平台与系统动态库仍需分别验证。
