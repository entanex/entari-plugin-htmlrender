---
title: 启动与生命周期
description: Entari add_service、Launart stages、热卸载与关闭语义
---

# 启动与生命周期

```yaml
plugins:
  htmlrender:
    provider: playwright
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

Provider discovery、availability 与 compose 不执行 I/O。`startup: off` 不会永久禁用Provider；第一个已获准 Provider operation 可以 lazy acquire runtime resource。

`HtmlRenderService` 不向业务代码暴露 `startup()`、`probe()` 或 `aclose()`。handler由 DI 获得 service 后，直接依赖 `service.renderer`、`service.templates`、`service.resources`、`service.graphics` 或 `service.capabilities`。不要读取内部runtime，也不要在 handler 中重建或替换 service 持有的 composition。
