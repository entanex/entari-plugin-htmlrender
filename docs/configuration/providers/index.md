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
| 第三方 Provider | 通过 `entari_plugin_htmlrender.providers` entry point 发现 |

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config: {}
```

`provider` 可为 `null`；此时 runtime 仍提供 Preparation、resource service、`render_template_html` 与显式启用的 Graphics capability，但 HTML 位图命令不可用。
