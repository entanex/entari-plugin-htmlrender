---
title: Provider 开发指南
description: 构建并验证第三方 HTML Provider distribution
---

# Provider 开发指南

第三方 Provider 应是独立 distribution，并在`entari_plugin_htmlrender.providers.v2` group 注册一个 `RenderProvider` 实例。

## 实现顺序

1. 定义严格校验的 `ConfigT`，由 `parse_config()` 一次生成。
2. 实现无 I/O `check_availability()`，返回 `ProviderAvailable()` 或带非空`reason`/`retryable` 的 `ProviderUnavailable` value。
3. 根据 executor transport 声明 `ResourceStrategy`。
4. 在无 I/O `compose()` 中接线 `ProviderBinding`。
5. 实现 failure-atomic/concurrency-safe lifecycle；`startup()` 或首个 admitted operation可以 lazy acquire，`probe()` 验证，`aclose()` drain 并释放。
6. 实现 `PreparedHtmlExecutor`，准确拒绝无法表达的 document feature/raster option。
7. 需要专属能力时定义 `CapabilityKey[Protocol]`，放入 `CapabilityCatalog`。

## 边界

Provider 只使用 `ProviderDependencies` 中的 admission、resources、publisher 与observers。worker、cache、native handle 由 adapter 内部拥有；不得 import Entari
integration、注册 service 或保存模块级 runtime。

底层依赖不可用时返回 `ProviderUnavailable` value；执行错误翻译为`ProviderExecutionError`，生命周期错误翻译为 `ProviderLifecycleError`。不支持的公共 raster option 使用 `UnsupportedRasterOptionError`；prepared document feature使用 `UnsupportedDocumentFeatureError(operation, feature, provider_id=...)`，其中`feature` 是稳定字符串（`DocumentRequirement` 应传 `.value`）。不能静默忽略。

测试至少覆盖 config 拒绝、availability/compose 无 I/O、parsed config identity、lazy acquire、startup/probe/close 幂等、startup rollback、close failure retry、并发close drain、每个 supported feature/option 以及 artifact metadata。可用`build_runtime_plan(config, provider_override=provider)` 构建 one-shot 测试计划；先在普通 Python 进程验证，再做 Entari service 集成。
