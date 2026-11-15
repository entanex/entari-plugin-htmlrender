---
title: 开始使用
description: 从安装到第一次 Entari 渲染的最短路径
icon: lucide/rocket
---

# 开始使用

本章从 Takumi 开始，把插件接入 Entari，在不安装浏览器的情况下完成静态内容渲染。完成快速开始后即可进入具体任务，其余页面按需要查阅：

- [快速开始](quickstart.md)：首次接入从这里开始，安装 Takumi、配置 `plugins.htmlrender`，并用 `HtmlRenderService` 完成第一次调用。
- [选择 Provider](choosing-provider.md)：需要浏览器能力或 Python 绘图时，比较 Takumi、远程 Playwright 和独立 Graphics backend。
- [升级到 0.2](migration-v0.2.md)：已有 0.1 项目先核对环境要求、公共入口和生命周期变化，再更新配置与调用。

Entari handler 接收 DI 注入的 `HtmlRenderService`；可复用业务函数收窄为`HtmlPreparer`、`HtmlRenderer`、`TemplateRenderer`、`ResourceAccess` 或 `GraphicsRenderer`。不要把 service/runtime 存入模块级全局变量。

## 下一步

- 要渲染 HTML、Markdown、文本或模板，继续阅读[渲染内容](../guides/rendering-content.md)和[模板与资源](../guides/templates-and-resources.md)。
- 要直接使用 Pillow 或 Skia 编写卡片，进入[Python 绘图](../guides/python-drawing.md)。
- 要调整启动、资源或后端参数，进入[配置与部署](../configuration/index.md)。
- 遇到安装或运行问题，直接查看[故障排查](../configuration/troubleshooting.md)。
