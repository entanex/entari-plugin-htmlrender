---
title: Provider 契约
description: 第三方 HTML Provider 的发现、设置、资源策略与 composition 协议
---

# Provider 契约

`EngineProvider[SettingsT]` 的稳定方法：

| 成员 | 要求 |
| --- | --- |
| `id` | 稳定的 lowercase ASCII ID；仅允许 `[a-z0-9._-]`，且首尾必须是字母或数字 |
| `parse_settings(raw)` | 把 `provider_config` 变成 typed settings，拒绝未知键 |
| `availability(settings)` | 无副作用检查依赖与平台，返回 `ProviderAvailability` |
| `resource_strategy(settings)` | 在接线前声明不可变 `ResourceStrategy` |
| `compose(settings, dependencies)` | 返回 `EngineBindings`，不读全局配置 |

`ProviderDependencies` 由 composition root 注入：共享 `operation_admission`、operation observer、cache observer、收窄的 `ProviderResources` 与可选 `AssetPublisher`。Provider 不得自行创建 filehost、observer 或资源服务。Provider 自定义 capability 的每个完整操作必须进入 `operation_admission.operation()`；若使用自有 lease，则其 lifecycle `aclose()` 必须先停止接纳、drain 全部 lease，再释放底层资源。

`EngineBindings` 包含 `RuntimeLifecycle`、可选 `PreparedHtmlExecutor` 与可选`CapabilityCatalog`。通用 executor 只接受 `PreparedHtml`、`RasterOptions`、`ResourcePolicy` 与 timeout；专属操作通过 capability 暴露。

## 发现

```toml
[project.entry-points."entari_plugin_htmlrender.providers"]
echo = "htmlrender_echo_provider:PROVIDER"
```

entry point 名必须等于 `provider.id`。`playwright`、`takumi` 是保留 ID；重复 ID、保留 ID 覆盖或加载对象不满足 runtime-checkable 协议都会在 composition 前失败。

完整最小实现见仓库的 [`examples/echo-provider`](../../examples/echo-provider/)。
