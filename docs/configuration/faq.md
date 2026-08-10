---
title: 常见问题
description: Provider、runtime、capability 与部署边界的常见选择
---

# 常见问题

## 为什么每次都要传 `runtime=`？

runtime 属于一个 Entari plugin lifetime。显式 `RuntimeSource` 让依赖和关闭边界可见，避免热卸载后仍有调用点持有进程全局对象。重复调用可在局部使用`runtime_context(service)`。

## 何时使用顶层函数，何时使用 `HtmlRenderer`？

常用业务路径使用 caller-first 顶层函数。需要持久化 typed request、探测`RenderCommand` 或直接组合 runtime 时使用 `HtmlRenderer`。

## Provider 和 Graphics backend 有什么区别？

Provider 消费 `PreparedHtml`，一次 runtime 选择一个。Pillow/Skia 消费`RasterScene`，可独立或同时启用，不读取 `provider_config`。

## 可以把 Page 或 native renderer 存成单例吗？

不可以。Playwright、Takumi 原生对象只在 capability 返回的异步上下文内有效；离开上下文或 service cleanup 后必须丢弃。

## 普通 import 会启动 Entari 吗？

不会。只有 Entari loader 注入插件上下文时包入口才注册 metadata 与 service；普通library import 保持无宿主副作用。
