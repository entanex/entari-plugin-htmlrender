---
title: 启动与生命周期
description: Entari add_service、Launart stages、热卸载与关闭语义
---

# 启动与生命周期

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
```

| 直接配置键 | 默认值 | 语义 |
| --- | --- | --- |
| `provider` | `null` | `playwright`、`takumi` 或第三方 Provider ID |
| `startup` | `off` | `OFF` 首次 operation lazy acquire；`WARMUP` eager startup；`PROBE` 再验证就绪 |
| `provider_config` | `{}` | 只交给选定 Provider 解析的配置 |

插件入口读取 `HtmlRenderConfig`，调用 `build_runtime_plan()` 完成一次无 I/O
composition，再通过 Entari `add_service` 注册 concrete `HtmlRenderService`。普通Python import 不注册服务，也不加载 Entari integration 或启动 adapter。

## Launart stages

| Stage | 行为 |
| --- | --- |
| `preparing` | 先启动显式 aiohttp filehost；`off` 不 eager startup，`warmup` 启动 Provider，`probe` 再执行最小就绪探测 |
| `blocking` | 等待 Launart 退出信号，不建立第二套生命周期 |
| `cleanup` | 停止接纳新操作、排空在途操作、关闭 runtime，再关闭 filehost；多个失败聚合报告 |

Entari sideload remove 与插件热卸载同样进入 cleanup。关闭失败保持可重试；若runtime 排空被取消，filehost 会继续存活，下一次 cleanup 从同一关闭边界重试。startup 失败会立即回滚已获得的资源，同时保留启动错误与回滚错误。

## disable / enable

禁用时，旧 service 完成 cleanup 后会登记新的 service，供下一次 enable 使用。新 service 在 Launart `preparing` 阶段才重建 plan、runtime、Provider transport 与绘图注册表；禁用期间不会因后台预构建而导入已配置的绘图模块。每个 generation 都有独立的 runtime admission、缓存、hosted filehost 与 Provider 生命周期。

卸载和原子 reload 不会为旧 owner 排队后继 generation；正在退出的 Launart 也不会。旧 generation 的 cleanup 失败时保持可重试，并且只有完整 cleanup 成功后才会登记供后续 enable 使用的新 generation。调用 `await disable_plugin(...)` 后，再调用 `await enable_plugin(...)`；直接使用 `Plugin.disable()` 时须等待它返回的 cleanup task 全部完成。重新启用后通过 DI 获取新的调用接口，旧 service 和 renderer 引用仍保持关闭状态。

如果受管理的启动或清理失败，service 会记录错误并完成框架阶段，避免 enable、disable 或 DI 无限等待。此时调用接口报 `RuntimeUnavailableError`，状态为 `failed`；需要显式 reload 插件才能恢复。reload 或卸载会再次尝试清理旧 runtime 与 filehost，单纯 enable 不会复用失败的 service。

Provider discovery、availability 与 compose 不执行 I/O。`startup: off` 不会永久禁用Provider；第一个已获准 Provider operation 可以 lazy acquire runtime resource。

`HtmlRenderService` 不向业务代码暴露 `startup()`、`probe()` 或 `aclose()`。handler 由 DI 获得 service 后，直接依赖 `service.preparation`、`service.renderer`、`service.templates`、`service.resources`、`service.graphics` 或 `service.capabilities`。不要读取内部 runtime，也不要在 handler 中重建或替换 service 持有的 composition。
