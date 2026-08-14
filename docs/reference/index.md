---
title: API 参考
description: 公共类型、方法、返回值、能力与失败语义的稳定契约
---

# API 参考

| 主题 | 页面 |
| --- | --- |
| Runtime、Entari service 与生命周期 | [Runtime API](runtime.md) |
| 内容、模板与图片产物 | [渲染 API](rendering.md) |
| Preparation 与资源访问 | [Preparation 与资源 API](preparation.md) |
| 专属能力 | [Capability 参考](capabilities.md) |
| 术语 | [术语表](glossary.md) |

公共模块保持 framework-neutral；只有 Entari loader 激活包时才注册`HtmlRenderService`。业务代码显式依赖 `HtmlRenderer`、`TemplateRenderer`、`ResourceAccess` 或 `GraphicsRenderer`，并返回 typed artifact。

本章描述稳定调用契约，不承担安装和运维说明。

## 下一步

要复制可运行调用，使用[使用指南](../guides/index.md)；要选择后端或配置生产环境，进入[配置与部署](../configuration/index.md)；要实现契约，进入[扩展开发](../extensions/index.md)。
