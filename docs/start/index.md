---
title: 开始使用
description: 从安装到第一次 Entari 渲染的最短路径
---

# 开始使用

本章把插件接入 Entari，并建立第一次可复用的渲染调用。推荐顺序：

1. [快速开始](quickstart.md)：安装 Provider、配置 `plugins.htmlrender`，并用`HtmlRenderService` 完成第一次调用。
2. [选择 Provider](choosing-provider.md)：比较 Playwright、Takumi 和独立 Graphics
   backend。
3. [渲染内容](../guides/rendering-content.md)：调用 HTML、Markdown、文本与模板 API。
4. [模板与资源](../guides/templates-and-resources.md)：设置路径白名单与资源策略。

Entari handler 接收 DI 注入的 `HtmlRenderService`；可复用业务函数收窄为`HtmlRenderer`、`TemplateRenderer`、`ResourceAccess` 或 `GraphicsRenderer`。不要把 service/runtime 存入模块级全局变量。

## 完成后

- 要实现具体渲染任务，继续阅读[使用指南](../guides/index.md)。
- 要调整启动、资源或后端参数，进入[配置与部署](../configuration/index.md)。
- 遇到安装或运行问题，直接查看[故障排查](../configuration/troubleshooting.md)。
