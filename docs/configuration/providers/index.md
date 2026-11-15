---
title: HTML Provider
description: Takumi、远程 Playwright 与第三方 Provider 的选择和配置入口
icon: lucide/boxes
---

# HTML Provider

Provider 消费 `PreparedHtml` 并产生 typed artifact。一次 runtime 只选择一个 HTML Provider；Pillow/Skia 不属于此类别。

| Provider | 状态 | 适用场景 |
| --- | --- | --- |
| [Takumi](takumi.md) | 推荐用于静态内容 | HTML、Markdown、文本和模板图片，以及节点、SVG、动画与字体接口 |
| [Playwright](playwright.md) | 推荐使用远程连接 | 浏览器布局、JavaScript、Markdown 公式、导航、selector 与页面原生能力 |
| 第三方 Provider | 由 Provider 决定 | 通过 `entari_plugin_htmlrender.providers.v2` entry point 发现 |

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    provider_config: {}
```

`provider` 可为 `playwright`、`takumi`、第三方 Provider ID 或 `null`。为 `null` 时 service 仍提供 `HtmlPreparer`、`TemplateRenderer`、`ResourceAccess` 与配置的 `GraphicsRenderer`，但 `HtmlRenderer` 的图片 operation 不可用。

本地 Playwright 浏览器安装、管理与启动将在不久的将来弃用，后续仅保留 remote support；当前本地模式仍可使用，尚未确定移除版本或日期。新部署与迁移步骤见[远程 Playwright](../remote-playwright.md)。

## 下一步

选定 Provider 后打开对应配置页，再回到[配置与部署](../index.md)完成生命周期、资源与生产环境设置。要实现第三方 Provider，转到[扩展开发](../../extensions/index.md)。
