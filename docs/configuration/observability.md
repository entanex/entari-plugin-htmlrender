---
title: 可选依赖与可观测性
description: 直接 Sentry SDK 与 Prometheus client 集成
---

# 可选依赖与可观测性

```bash
uv add "entari-plugin-htmlrender[sentry,prometheus]>=0.8.0,<0.9"
```

```yaml
plugins:
  htmlrender:
    observability:
      sentry: true
      prometheus: true
```

完整配置路径是 `observability.sentry` 与 `observability.prometheus`，默认均为`false`。

adapter 直接惰性导入 `sentry_sdk` 与 `prometheus_client`；不要求额外的框架集成插件。应用仍负责初始化 Sentry SDK、配置采样并暴露 Prometheus registry。缺少可选 SDK 时记录诊断并保持 no-op，不改变渲染契约。

| 含义 | Prometheus | Sentry |
| --- | --- | --- |
| 操作次数 | `entari_htmlrender_operations_total` | `entari.htmlrender.count` |
| 操作耗时 | `entari_htmlrender_duration_seconds` | `entari.htmlrender.duration` |
| 缓存事件 | `entari_htmlrender_cache_events` | `entari.htmlrender.cache.events` |
| 缓存条目 | `entari_htmlrender_cache_entries` | `entari.htmlrender.cache.entries` |
| 缓存驻留字节 | `entari_htmlrender_cache_resident_bytes` | `entari.htmlrender.cache.resident_bytes` |

标签/attributes 保持低基数，主要包括 `op`、`backend`、`status`。Playwright 原生对象和 Takumi raw renderer 不被代理；typed htmlrender 边界才提供稳定 operation与错误分类。
