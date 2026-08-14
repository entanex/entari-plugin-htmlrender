---
title: 常见问题
description: Provider、service、capability 与部署边界的常见选择
---

# 常见问题

## 为什么业务函数要接收 contract？

renderer/resource/capability 都属于一次 Entari plugin lifetime。显式依赖让能力和关闭边界可见，避免热卸载后仍有调用点持有进程全局对象。handler 接收`HtmlRenderService`，再把 `.renderer` 等最小 contract 传给业务函数。

## 何时使用 `HtmlRenderer`，何时使用 `TemplateRenderer`？

图片输出使用 `HtmlRenderer.rasterize_*()`；模板 HTML 输出使用`TemplateRenderer.render()`。输入类型和输出 artifact 不通过 request DTO 或 flag 改变。

## Provider 和 Graphics backend 有什么区别？

HTML Provider 消费 `PreparedHtml`，一次 composition 最多选择一个。Pillow/Skia 消费`RasterScene`，由 `graphics.backend` 独立选择，不读取 `provider_config`。

## 可以把 Page 或 native renderer 存成单例吗？

不可以。Playwright、Takumi 原生对象只在 capability 返回的异步 lease 内有效；离开上下文或 service cleanup 后必须丢弃。

## 普通 import 会启动 Entari 吗？

不会。只有 Entari loader 注入插件上下文时包入口才注册 metadata 与 service；普通library import 保持无宿主副作用。
