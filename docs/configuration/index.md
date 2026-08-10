---
title: 配置总览
description: Entari htmlrender 插件的严格配置模型
---

# 配置总览

Entari 插件短名为 `htmlrender`。配置值直接映射到 `RenderSettings`，不存在额外wrapper：

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
    html:
      max_pixels: 16777216
      max_concurrency: 2
    graphics:
      backends: [pillow]
    resources:
      local_access:
        allowed_paths: [assets, templates]
      remote_access:
        allow_hosts: [cdn.example.com]
    observability:
      sentry: false
      prometheus: true
```

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `provider` | `null` | HTML Provider ID |
| `startup` | `off` | `off`、`warmup`、`probe` |
| `provider_config` | `{}` | 所选 Provider 的专属配置 |
| `html` | 见 [HTML 预算](html-rendering.md) | 跨 Provider 的输入、像素、输出与并发限制 |
| `graphics` | 无 backend | Pillow/Skia `RasterScene` 能力 |
| `resources` | 安全默认值 | 缓存、模板、遍历、本地/远程访问与 filehost |
| `observability` | 全关闭 | 直接 Sentry SDK / Prometheus client adapter |

所有模型使用 `extra="forbid"`；未知键和类型错误在 Entari 配置阶段失败。Provider专属键只能位于 `provider_config`，不能泄漏进顶层模型。
