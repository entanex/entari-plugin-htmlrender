---
title: 开始使用
description: 从安装到第一次 Entari 渲染的最短路径
---

# 开始使用

推荐顺序：

1. [快速开始](quickstart.md)：安装 Provider、配置 `plugins.htmlrender`，并用`HtmlRenderService` 完成第一次调用。
2. [选择渲染后端](choosing-provider.md)：比较 Playwright、Takumi 和独立 Graphics
   capability。
3. [渲染内容](../guides/rendering-content.md)：调用 HTML、Markdown、文本与模板 API。
4. [模板与资源](../guides/templates-and-resources.md)：设置路径白名单与资源策略。

业务函数应接收 `RuntimeSource`，或接收 Entari DI 注入的 `HtmlRenderService`；不要把 runtime 存入模块级全局变量。
