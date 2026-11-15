---
title: 使用指南
description: 使用稳定公共 API 完成内容、模板、浏览器与图形渲染任务
icon: lucide/list-checks
---

# 使用指南

本章按内容渲染、Python 绘图、组合与集成排列。第一次使用时，先按[开始使用](../start/index.md)完成安装和首张图片渲染；已有项目可以直接选择任务。

## 内容渲染

| 目标 | 章节 |
| --- | --- |
| 把 HTML、Markdown、文本或 Jinja 模板转换为图片 | [渲染内容](rendering-content.md) |
| 组织模板、图片、字体和样式 | [模板与资源](templates-and-resources.md) |
| 导航网页或截取指定元素 | [操作浏览器页面](browser-automation.md) |

## Python 与场景绘图

| 目标 | 章节 |
| --- | --- |
| 用 Python 编写卡片，加载绘图文件并重载源码 | [Python 绘图](python-drawing.md) |
| 绘制后端中立的像素场景 | [绘制 RasterScene](raster-scenes.md) |

## 组合与集成

| 目标 | 章节 |
| --- | --- |
| 切换 HTML 后端，或在同一服务中选择 Pillow/Skia | [多引擎与切换](switching-engines.md) |
| 约束生命周期、超时和错误处理 | [最佳实践](best-practices.md) |

任务页链接仓库中的可运行示例；示例展示组合方式，稳定契约仍以参考手册为准。

## 下一步

- 准备部署时，根据[配置与部署](../configuration/index.md)核对生命周期、访问策略、预算与可观测性。
- 需要精确签名时，转到[API 参考](../reference/index.md)。
- 要增加新的 HTML 实现时，进入[扩展开发](../extensions/index.md)，不要让业务调用依赖具体 Provider。
