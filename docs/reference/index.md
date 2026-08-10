---
title: 参考
description: API、配置、Provider 与 capability 的稳定契约入口
---

# 参考

| 主题 | 页面 |
| --- | --- |
| Runtime 与生命周期 | [Runtime API](runtime.md) · [启动与生命周期](../configuration/lifecycle.md) |
| 通用调用 | [渲染 API](rendering.md) · [Preparation 与资源 API](preparation.md) |
| 专属能力 | [Capability 参考](capabilities.md) |
| 配置 | [配置总览](../configuration/index.md) · [资源策略](../configuration/resources.md) |
| HTML Provider | [Playwright](../configuration/providers/playwright.md) · [Takumi](../configuration/providers/takumi.md) |
| Graphics backend | [Pillow](../configuration/graphics/pillow.md) · [Skia](../configuration/graphics/skia.md) |
| 术语 | [术语表](glossary.md) |

公共模块保持 host-neutral；只有 Entari loader 激活包时才注册`HtmlRenderService`。业务代码依赖 `RuntimeSource` 与 typed artifact，不依赖宿主容器。
