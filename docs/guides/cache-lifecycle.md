---
title: 缓存组件与调优
description: Resource、Jinja、filehost 与 native runtime 缓存的所有权
---

# 缓存组件与调优

缓存均有界并属于一次 runtime/service 生命周期，观测名称分别为 `resource`、`template_environment`、`filehost` 与 `takumi_compiled`：

| 组件 | 失效方式 | 完整释放 |
| --- | --- | --- |
| Resource Reader | validator 自动复查；单次读取可 `refresh=True` | `await runtime.resources.clear()` 或 service cleanup |
| Jinja environment | template auto-reload、environment LRU | service cleanup |
| Filehost mapping/store | TTL、容量与 lease | service cleanup 释放当前 namespace，并关闭 aiohttp server |
| Takumi compiled/native state | capability 自有缓存规则 | service cleanup；继续服务需新 runtime |

`runtime.resources.clear()` 只清理当前 RenderRuntime 的 Resource Reader，不会清理 Jinja Environment、filehost、Playwright 或 Takumi 状态。不要为了清一个资源关闭 service；用`read_bytes(reference, refresh=True)` 或 `read_text(..., refresh=True)`。

Jinja environment cache key 同时包含 extension、filter 的名称和 callable 身份；高基数动态 filter 会造成持续抖动，无法通过单纯增加内存解决。Takumi 通过`api.compiled_cache_stats` 暴露只读的 hit/miss/entry/weight 快照。

cleanup 开始后 admission gate 拒绝新操作，并等待所有在途 cache/resource/capability操作完成。关闭失败可重试，但 runtime 一旦进入 closing 就不能恢复服务；由 Entari重新加载插件以取得新 service。

Prometheus 缓存指标使用 `entari_htmlrender_cache_events`、`entari_htmlrender_cache_entries` 与 `entari_htmlrender_cache_resident_bytes`。
