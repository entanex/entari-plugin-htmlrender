---
title: Provider 契约
description: 第三方 HTML Provider 的发现、配置、资源策略与 composition 协议
---

# Provider 契约

`RenderProvider[ConfigT]` 的稳定成员：

| 成员 | 要求 |
| --- | --- |
| `id` | 稳定 lowercase ASCII ID；仅允许 `[a-z0-9._-]`，首尾为字母或数字 |
| `parse_config(raw)` | 把 `provider_config` 变成 Provider-owned typed config，拒绝未知键 |
| `check_availability(config)` | 无 I/O 检查依赖/平台，返回 `ProviderAvailable` 或 `ProviderUnavailable` |
| `resource_strategy(config)` | 在接线前声明不可变 `ResourceStrategy` |
| `compose(config, dependencies)` | 无 I/O 返回 `ProviderBinding`，不读全局配置 |

parsed config 的 identity 从 `parse_config()` 一直传到 availability、resource strategy与 compose；composition 不复制或重建这个 Provider-owned value。

`ProviderDependencies` 注入共享 `operation_admission`、operation observer、cache
observer、收窄的 `ProviderResourceAccess` 与可选 `AssetPublisher`。Provider 不得自行创建 filehost、observer 或资源服务。自定义 capability 的完整公开操作必须进入共享admission；若 adapter 使用自有 lease，lifecycle `aclose()` 必须先停止接纳、drain全部 lease，再释放底层资源。

`ProviderBinding` 包含 `RuntimeLifecycle`、可选 `PreparedHtmlExecutor` 与可选`CapabilityCatalog`。executor 接受 `PreparedHtml`、`RasterOptions`、外层`RenderOperation` 与可选 `ResourceMaterializationPolicy`；专属操作通过 capability暴露。

## Lifecycle

- discovery、availability 与 compose 不执行 I/O、不获得 runtime resource。
- `startup()` 或第一个已获准 Provider operation 可以 lazy acquire；因此`startup: off` 表示 lazy，而不是永久禁用 Provider。
- `startup()` failure-atomic、并发安全且在成功回滚后可重试；回滚失败会 poison
  composition。
- `probe()` 只验证已启动 runtime，不改变 ownership。
- `aclose()` 对未启动、部分启动、已启动和 poisoned 状态幂等，并尽力释放所有已获资源。

## 发现

```toml
[project.entry-points."entari_plugin_htmlrender.providers.v2"]
echo = "htmlrender_echo_provider:PROVIDER"
```

entry point 名必须等于 `provider.id`。`playwright`、`takumi` 是保留 ID；重复 ID、保留 ID 覆盖或加载对象不满足 runtime-checkable protocol 都会在 composition 失败。

`build_runtime_plan(config, provider_override=provider)` 只覆盖配置所选的这一个Provider，不接受候选 Provider sequence。完整最小实现见仓库的[`examples/echo-provider`](../../examples/echo-provider/)。
