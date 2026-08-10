---
title: 故障排查
description: 从配置、runtime 绑定、Provider、资源与关闭阶段定位失败
---

# 故障排查

## `RuntimeNotBound`

便利函数没有收到 `runtime=`，当前 task 也未进入 `runtime_context(...)`。在 Entari
handler 中让 DI 注入 `HtmlRenderService`，并传 `runtime=service`。不要安装模块级默认 runtime。

## `ProviderNotFound` / `ProviderUnavailable`

确认 `provider` 拼写、对应 extra 已安装、第三方 distribution 的 entry point group为 `entari_plugin_htmlrender.providers`。`ProviderUnavailable` 的稳定 message 描述依赖、平台或连接前置条件；底层 cause 仅用于诊断。本地 Playwright 报告 executable不存在时，安装与当前 Python client 精确匹配的 browser revision；不要从其他虚拟环境复制 browser cache。

## `CapabilityUnavailable`

`provider: null` 或所选 Provider 没有绑定该命令/extension。用`HtmlRenderer.supports(RenderCommand...)` 或 `runtime.extensions.names()` 检查能力，不要捕获后静默降级为不同语义。

## 本地资源被拒绝

把解析后的最小目录加入 `resources.local_access.allowed_paths`。工作目录和`template_base` 不会隐式授予访问权。需要确定性失败时使用`ResourcePolicy.STRICT`。

## Filehost 无法启动

确认安装 `filehost` extra，`public_base_url` 是浏览器可达的绝对 URL，bind port未冲突，反向代理把固定 path 映射到 aiohttp server。该服务不使用 Entari 的 HTTP路由。

## 关闭卡住

cleanup 会先停止接收新操作，再等待在途调用释放 admission/capability lease。检查是否有 Playwright Page、Takumi API 或资源调用逃逸出其上下文。不要强行复用进入 closing 状态的 runtime；失败关闭可重试。
