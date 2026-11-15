---
title: 配置与部署
description: 配置后端、生命周期、资源边界与生产运行环境
icon: lucide/settings-2
---

# 配置与部署

本章按“加载配置 → 设置后端 → 约束资源与预算 → 诊断问题”的顺序组织。先通过下方的完整配置了解入口，再按需要查阅字段；具体调用方法见[使用指南](../guides/index.md)。

| 分组 | 阅读顺序 |
| --- | --- |
| 基础配置 | [环境变量与配置文件](dotenv.md) · [启动与生命周期](lifecycle.md) |
| HTML Provider | [Provider 总览](providers/index.md) · [Takumi](providers/takumi.md) · [Playwright](providers/playwright.md) · [远程 Playwright](remote-playwright.md) |
| 绘图后端 | [绘图后端总览](graphics/index.md) · [Pillow](graphics/pillow.md) · [Skia](graphics/skia.md) |
| 资源与预算 | [资源与访问策略](resources.md) · [安全须知](security.md) · [HTML 渲染预算](html-rendering.md) · [缓存组件与调优](../guides/cache-lifecycle.md) |
| 诊断与排障 | [可选依赖与可观测性](observability.md) · [故障排查](troubleshooting.md) · [常见问题](faq.md) |

要更换已有项目的引擎或同时启用多个绘图后端，按[多引擎与切换](../guides/switching-engines.md)操作。

## 配置入口

Entari 插件短名为 `htmlrender`。`plugins.htmlrender` 的值直接交给`entari_plugin_htmlrender.config.HtmlRenderConfig` 校验，不存在额外 wrapper：

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    html:
      max_pixels: 16777216
      max_concurrency: 2
    graphics:
      backends: [pillow, skia]
    resources:
      local_access:
        allowed_paths: [assets, templates]
      remote_access:
        allow_hosts: [cdn.example.com]
    observability:
      sentry: false
      prometheus: true
```

示例用 Takumi 处理静态内容，其他可选后端与可观测性能力需安装对应 extra。中文字体配置见 [Takumi](providers/takumi.md#fonts)。需要浏览器能力时，推荐[远程 Playwright](remote-playwright.md)；本地浏览器安装、管理与启动计划在不久的将来弃用，后续仅保留 remote support，当前本地模式仍可使用。

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `provider` | `null` | HTML Provider ID；`null` 时只保留模板到 HTML、资源与图形服务 |
| `startup` | `off` | `off` 为首次 Provider operation lazy acquire；`warmup` / `probe` 由 Entari service eager 执行 |
| `provider_config` | `{}` | 只交给所选 Provider 解析的配置 |
| `html` | 见 [HTML 预算](html-rendering.md) | 跨 Provider 的输入、像素、输出与并发限制 |
| `graphics` | `backends: []` | 可并行启用的 Pillow/Skia `GraphicsRenderer`；首项为主入口 |
| `resources` | 安全默认值 | 缓存、模板、遍历、本地/远程访问与 filehost |
| `observability` | 全关闭 | Sentry SDK / Prometheus client adapter |

所有 plugin-owned 模型均使用 `extra="forbid"`。未知键、拼写错误与类型错误会在Entari 配置阶段失败；Provider 专属键只能放在 `provider_config` 中。

框架无关的高级嵌入也复用同一个 `HtmlRenderConfig`，通过 `entari_plugin_htmlrender.composition.build_runtime_plan()` 构建一次性的 `RuntimePlan`。创建 plan 完成配置解析和后端选择，不启动服务器或渲染引擎；`build_runtime()` 恰好消费一次，宿主传入的绘图注册表工厂可以在此时读取、加载源码。运行时的启动和关闭仍由创建它的宿主负责。Entari 的归属和重载流程见[插件生命周期与重载](../extensions/entari-lifecycle.md)。测试可用 kw-only `provider_override=` 注入配置所选的单个 Provider。

## 下一步

完成配置后用[快速开始](../start/quickstart.md)中的调用做部署冒烟测试；若需要确认公开对象的精确契约，查阅[API 参考](../reference/index.md)。
