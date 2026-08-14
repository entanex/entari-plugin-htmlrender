---
title: 配置与部署
description: 配置后端、生命周期、资源边界与生产运行环境
---

# 配置与部署

本章回答“怎样让既定渲染任务在目标环境中可靠运行”。先选择需要决策的边界，再查阅具体字段：

| 决策 | 入口 |
| --- | --- |
| 选择 HTML Provider 或 Graphics 后端 | [HTML Provider](providers/index.md) · [Graphics 后端](graphics/index.md) |
| 决定启动时机、关闭顺序与失败行为 | [启动与生命周期](lifecycle.md) |
| 设置 HTML、图形、缓存与并发预算 | [HTML 渲染预算](html-rendering.md) · [缓存组件与调优](../guides/cache-lifecycle.md) |
| 授权本地、远程与模板资源 | [资源与访问策略](resources.md) · [安全须知](security.md) |
| 连接远程浏览器 | [远程 Playwright](remote-playwright.md) |
| 建立生产诊断能力 | [可选依赖与可观测性](observability.md) · [故障排查](troubleshooting.md) |

## 配置入口

Entari 插件短名为 `htmlrender`。`plugins.htmlrender` 的值直接交给`entari_plugin_htmlrender.config.HtmlRenderConfig` 校验，不存在额外 wrapper：

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
      backend: pillow
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
| `provider` | `null` | HTML Provider ID；`null` 时只保留模板到 HTML、资源与图形服务 |
| `startup` | `off` | `off` 为首次 Provider operation lazy acquire；`warmup` / `probe` 由 Entari service eager 执行 |
| `provider_config` | `{}` | 只交给所选 Provider 解析的配置 |
| `html` | 见 [HTML 预算](html-rendering.md) | 跨 Provider 的输入、像素、输出与并发限制 |
| `graphics` | `backend: null` | 可选的 Pillow/Skia `GraphicsRenderer` |
| `resources` | 安全默认值 | 缓存、模板、遍历、本地/远程访问与 filehost |
| `observability` | 全关闭 | Sentry SDK / Prometheus client adapter |

所有 plugin-owned 模型均使用 `extra="forbid"`。未知键、拼写错误与类型错误会在Entari 配置阶段失败；Provider 专属键只能放在 `provider_config` 中。

框架无关的高级嵌入也复用同一个 `HtmlRenderConfig`，通过`entari_plugin_htmlrender.composition.build_runtime_plan()` 构建 one-shot `RuntimePlan`。`build_runtime()` 恰好消费一次；构建 plan/runtime 不执行外部 I/O，生命周期仍由创建它的宿主负责。测试可用 kw-only `provider_override=` 注入配置所选的单个 Provider。

## 下一步

完成配置后用[快速开始](../start/quickstart.md)中的调用做部署冒烟测试；若需要确认公开对象的精确契约，查阅[API 参考](../reference/index.md)。
