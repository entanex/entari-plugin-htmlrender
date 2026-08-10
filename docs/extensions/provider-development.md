---
title: Provider 开发指南
description: 构建并验证第三方 HTML Provider distribution
---

# Provider 开发指南

第三方 Provider 应是独立 distribution，并在`entari_plugin_htmlrender.providers` group 注册一个 `EngineProvider` 实例。

## 实现顺序

1. 定义不可变或严格校验的 `SettingsT`。
2. 实现无副作用 `availability()`；不要在发现阶段启动线程或连接服务。
3. 根据 executor 的资源 transport 声明 `ResourceStrategy`。
4. 实现幂等/concurrency-safe lifecycle：startup、probe、aclose。
5. 实现 `PreparedHtmlExecutor`，准确拒绝无法表达的 requirement/option。
6. 需要专属能力时定义 `CapabilityKey[Protocol]`，放入 `CapabilityCatalog`。

## 边界

Provider 只使用 `ProviderDependencies` 中的 operation admission、resources、publisher 与 observers。worker、缓存、native handle 由 adapter 内部拥有；不得 import `host`、调用 Entari config API、注册 service 或保存模块级 runtime。自定义 capability 应在 `dependencies.operation_admission.operation()` 中覆盖完整操作；采用 adapter 自有 lease 时，必须在 lifecycle shutdown 中停止接纳并 drain。

底层依赖不可用时返回 `ProviderAvailability(False, reason)`；执行错误翻译为`ProviderExecutionError`，生命周期错误由 runtime 收束为 `ProviderLifecycleError`。不支持的公共选项使用 `UnsupportedRenderOption`，不能静默忽略。

测试至少覆盖设置拒绝、availability 无副作用、startup/probe/close 幂等、startup
rollback、close failure retry、并发 close drain、每个 supported requirement/option以及 artifact 元数据。先在普通 Python 进程验证 Provider，再做 Entari service 集成。
