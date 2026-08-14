---
title: 故障排查
description: 从配置、runtime、Provider、资源与关闭阶段定位失败
---

# 故障排查

## `RuntimeUnavailableError`

调用发生在 runtime 进入 `closing` / `closed` 后。检查是否缓存了旧 service 或 facade；插件 reload 后应由 Entari DI 提供新 service。依赖只在 composition/DI 边界显式解析。

## `ProviderNotFoundError` / `ProviderUnavailableError`

确认 `provider` 拼写、对应 extra 已安装、第三方 distribution 的 entry-point group为 `entari_plugin_htmlrender.providers.v2`。使用 `provider_id`、`reason` 与`retryable` 字段分支，底层 cause 只用于诊断。本地 Playwright 报告 executable 缺失时，安装与当前 Python client 精确匹配的 browser revision；不要复制其他虚拟环境的browser cache。

## `CapabilityUnavailableError`

所选 Provider 没有组合目标 capability。用 `service.capabilities.available_names` 或typed key 的 `get()` 探测；不要捕获后静默降级为不同语义。HTML operation 则用`renderer.supports(RenderOperation...)` 探测。

## `GraphicsBackendUnavailableError`

确认 `graphics.backend` 与安装的 `pillow` / `skia` extra 一致，并检查 native wheel和动态库支持。Graphics 不通过 capability catalog 提供，也不会自动回退到另一实现。

## 本地资源被拒绝

把最小目录加入 `resources.local_access.allowed_paths`。工作目录、`TemplateRef.root`和 HTML `<base>` 不会隐式授予访问权。需要确定性失败时，在 rasterize 调用传入`ResourceMaterializationPolicy.STRICT`。

## Filehost 无法启动

确认安装 `filehost` extra，`public_base_url` 是 consumer 可达的绝对 URL，bind port未冲突，反向代理把固定 path 映射到 aiohttp server。该服务不使用 Entari HTTP 路由。

## 关闭卡住

cleanup 会先停止接收新操作，再等待在途调用释放 admission/capability/publication
lease。检查是否有 Playwright Page、Takumi session/native renderer 或 publication逃逸出其上下文。不要复用进入 closing 状态的 runtime；失败关闭可重试。
