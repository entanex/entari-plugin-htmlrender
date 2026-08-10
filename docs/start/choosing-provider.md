---
title: 选择渲染后端
description: Playwright、Takumi 与 Graphics capability 的选择边界
---

# 选择渲染后端

`provider` 只选择 HTML 执行引擎；Pillow 与 Skia 是独立的 `RasterScene`
capability，不参与 Provider 选择。

| 后端 | 适用需求 | 主要代价 |
| --- | --- | --- |
| Playwright | 浏览器布局、JavaScript、导航、selector 截图 | 浏览器进程或兼容远程 endpoint |
| Takumi | 无浏览器静态 HTML、node、SVG、animation | 依赖受支持平台的 native wheel |
| Pillow | 物理像素矩形场景，不需要 HTML 布局 | Python image stack，能力面刻意较小 |
| Skia | 同一 `RasterScene` 的 Skia 实现 | wheel 与系统图形库的平台约束 |

首次接入通用 HTML 渲染优先 Playwright；生产环境通常把浏览器放在独立容器并通过CDP/WS 连接。只有确认内容不依赖浏览器语义时才切换 Takumi。业务只使用provider-neutral `render_*` API 时，切换 Provider 不改变调用形态。

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    graphics:
      backends: [pillow]
```

选择 extra 只安装 Python distribution；远程服务版本、浏览器二进制、native wheel平台与系统动态库仍需分别验证。
