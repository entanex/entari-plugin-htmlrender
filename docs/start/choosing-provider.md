---
title: 选择 Provider
description: Playwright、Takumi 与 Graphics backend 的选择边界
---

# 选择 Provider

`provider` 只选择 HTML raster Provider；Pillow/Skia 实现独立的`GraphicsRenderer`，不参与 Provider 选择。

| 实现 | 适用需求 | 主要代价 |
| --- | --- | --- |
| Playwright | 浏览器布局、JavaScript、导航、selector 截图 | 浏览器进程或兼容远程 endpoint |
| Takumi | 无浏览器静态 HTML、SVG、动态字体 | 依赖受支持平台的 native wheel |
| Pillow | 物理像素矩形场景，不需要 HTML 布局 | Python image stack，能力面刻意较小 |
| Skia | 同一 `RasterScene` 的 Skia 实现 | wheel 与系统图形库的平台约束 |

首次接入通用 HTML rasterization 优先 Playwright；生产环境通常把浏览器放在独立容器并通过 CDP/WS 连接。只有确认内容不依赖浏览器语义时才切换 Takumi。业务只依赖`HtmlRenderer` 时，切换 Provider 不改变调用形态。

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    graphics:
      backend: pillow
```

选择 extra 只安装 Python distribution；远程服务版本、浏览器二进制、native wheel平台与系统动态库仍需分别验证。
