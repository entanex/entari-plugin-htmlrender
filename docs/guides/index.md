---
title: 使用指南
description: 使用稳定公共 API 完成内容、模板、浏览器与图形渲染任务
icon: lucide/list-checks
---

# 使用指南

本章回答“怎样完成一件渲染任务”，不要求从头读到尾。首次接入沿入门路径前进；已有项目直接选择任务。配置、部署与运维集中在[配置与部署](../configuration/index.md)，字段、类型和错误契约集中在[API 参考](../reference/index.md)。

## 首次接入

1. [快速开始](../start/quickstart.md)：使用默认推荐的 Playwright 完成第一张图片。
2. [选择 Provider](../start/choosing-provider.md)：比较 HTML Provider 与 Graphics backend 的能力和环境约束。
3. [渲染内容](rendering-content.md)：接入 HTML、Markdown、文本或 Jinja 模板。
4. 按需查阅[配置与部署](../configuration/index.md)，不要预先阅读全部配置字段。

## 按任务进入

| 目标 | 章节 |
| --- | --- |
| 组织模板、图片、字体和样式 | [模板与资源](templates-and-resources.md) |
| 导航网页或截取指定元素 | [操作浏览器页面](browser-automation.md) |
| 绘制后端中立的像素场景 | [绘制 RasterScene](raster-scenes.md) |
| 约束生命周期、超时和错误处理 | [最佳实践](best-practices.md) |

任务页链接仓库中的可运行示例；示例展示组合方式，稳定契约仍以参考手册为准。

## 下一步

- 准备部署时，根据[配置与部署](../configuration/index.md)核对生命周期、访问策略、预算与可观测性。
- 需要精确签名时，转到[API 参考](../reference/index.md)。
- 要增加新的 HTML 实现时，进入[扩展开发](../extensions/index.md)，不要让业务调用依赖具体 Provider。
