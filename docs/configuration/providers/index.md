---
title: HTML Provider
description: Playwright、Takumi 与第三方 Provider 的选择和配置入口
---

# HTML Provider

Provider 消费 `PreparedHtml` 并产生 typed artifact。一次 runtime 只选择一个 HTML
Provider；Pillow/Skia 不属于此类别。

| Provider | 适用场景 |
| --- | --- |
| [Playwright](playwright.md) | 浏览器布局、JavaScript、导航与页面原生能力 |
| [Takumi](takumi.md) | 无浏览器静态渲染，以及 node/SVG/animation 专属能力 |
| 第三方 Provider | 通过 `entari_plugin_htmlrender.providers.v2` entry point 发现 |

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config: {}
```

`provider` 可为 `null`；此时 service 仍提供 `TemplateRenderer`、`ResourceAccess` 与配置的 `GraphicsRenderer`，但 `HtmlRenderer` 的图片 operation 不可用。

## 下一步

选定 Provider 后打开对应配置页，再回到[配置与部署](../index.md)完成生命周期、资源与生产环境设置。要实现第三方 Provider，转到[扩展开发](../../extensions/index.md)。
