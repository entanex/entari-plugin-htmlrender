---
title: 选择 Provider
description: 从 Takumi 静态渲染开始，按需选择远程 Playwright 或 Python 绘图
---

# 选择 Provider

`provider` 只选择 HTML raster Provider；Pillow/Skia 实现独立的 `GraphicsRenderer`，不参与 Provider 选择。

静态卡片、帮助菜单和模板图片推荐先使用 Takumi，不需要部署浏览器。依赖 JavaScript、浏览器布局、网页导航或选择器截图时，使用远程 Playwright。已有浏览器模板应先确认 Takumi 的 HTML/CSS 支持范围与实际排版效果。

| 实现 | 适用需求 | 主要代价 |
| --- | --- | --- |
| Takumi | 静态 HTML、Markdown、文本与模板；专属接口支持 SVG、字体、测量与动画 | HTML/CSS 支持有限；中文需配置字体；依赖平台 wheel |
| Playwright | 浏览器布局、JavaScript、Markdown 公式、导航、选择器截图 | 推荐远程部署，需要独立浏览器服务与兼容的 WS/CDP endpoint |
| Pillow | Python 绘图函数或 `RasterScene`，不需要 HTML 布局 | 不解析 HTML/Markdown；需安装 `[pillow]` |
| Skia | Python 绘图函数或 `RasterScene`，使用 Skia 绘制 | 不解析 HTML/Markdown；wheel 与系统图形库有平台约束 |

!!! warning "本地 Playwright 弃用计划"

    本地 Playwright 浏览器安装、管理与启动将在不久的将来弃用，后续仅保留 remote support。当前版本仍支持本地模式，尚未确定移除版本或日期。新部署请参考[远程 Playwright](../configuration/remote-playwright.md)：Bot 环境只需安装 `[playwright]` Python 客户端，无需执行 `playwright install`。

Markdown 数学走 `pymdownx.arithmatex` 的 generic 标记管线。需要让包内 KaTeX 初始化脚本仅针对带 `data-htmlrender-arithmatex` 的生成容器完成排版时选择 Playwright。含公式的 preparation 可以成功，但它会设置 `DocumentRequirement.JAVASCRIPT`，Takumi rasterization 会以 `UnsupportedDocumentFeatureError` 拒绝；若静态 Provider 必须输出可见公式，应先把公式转换为无需客户端脚本的静态 HTML/SVG。

Pillow 与 Skia 可在 `graphics.backends` 中同时启用。首项作为 `service.graphics` 默认 renderer，也可用兼容字段 `graphics.backend` 指定主入口；两者同时配置时，`backend` 必须出现在 `backends` 中。启用后可分别通过 `service.capabilities.pillow` 与 `service.capabilities.skia` 选择实现。

业务只依赖 `HtmlRenderer` 时，Provider 切换不改变 `rasterize_html()` 等便捷方法或 `rasterize_prepared()` 的调用形态，但内容必须符合所选后端的能力边界。以下配置以 Takumi 处理静态内容，并独立启用 Pillow 绘图；需要同时安装 `[takumi,pillow]`。

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    graphics:
      backend: pillow
```

Takumi 的字体、缓存和高级接口见 [Takumi 配置与能力](../configuration/providers/takumi.md)。选择 extra 只安装 Python distribution；远程服务版本、浏览器二进制、native wheel 平台与系统动态库仍需分别验证。
