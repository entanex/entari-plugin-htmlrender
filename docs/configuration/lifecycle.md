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
| `startup` | `off` | `off`、`warmup`、`probe` |
| `provider_config` | `{}` | 只交给选定 Provider 解析的设置 |

`RenderStartupMode` 是 `startup` 字段对应的公开 enum。

插件入口读取 `RenderSettings`，完成一次 composition，然后通过 Entari
`add_service` 注册 `HtmlRenderService`。普通 Python import 不注册服务，也不启动adapter。

## Launart stages

| Stage | 行为 |
| --- | --- |
| `preparing` | 先启动显式 aiohttp filehost；若选择 Provider 且 startup 非 `off`，调用 runtime startup；`probe` 再执行最小探测 |
| `blocking` | 等待 Launart 退出信号，不建立第二套生命周期 |
| `cleanup` | 停止接收新操作、drain 在途操作、关闭 runtime，再关闭 filehost；多个失败会聚合 |

Entari sideload remove/插件热卸载同样进入 cleanup。`HtmlRenderService.aclose()` 成功后幂等；关闭失败保持可重试。startup 失败会立即尝试回滚，且同时保留启动与清理错误。

handler 应由 DI 注入 `HtmlRenderService`，调用时传 `runtime=service`。不要在 handler中 startup、重建或替换 service 持有的 runtime。
