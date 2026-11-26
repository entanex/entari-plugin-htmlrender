---
title: 配置总览与运行机制
description: HtmlRenderConfig 顶层结构、环境变量注入、启动策略与 HTML 渲染预算
icon: lucide/settings-2
---

# 配置总览与运行机制

插件在 Entari 中的短名为 `htmlrender`。所有配置项都直接写在 `plugins.htmlrender` 下，由 `HtmlRenderConfig` 严格校验——任何未知字段、拼写错误或类型不匹配都会在配置加载阶段立即报错（`extra="forbid"`）。

## 完整配置示例

```yaml
plugins:
  htmlrender:
    provider: takumi # (1)!
    startup: probe   # (2)!
    provider_config: # (3)!
      font_families: ["Noto Sans SC"]
    html:            # (4)!
      max_pixels: 16777216
      max_concurrency: 2
    graphics:        # (5)!
      backends: [pillow]
    resources:       # (6)!
      local_access:
        allowed_paths: [templates, assets, fonts]
      remote_access:
        allow_hosts: [cdn.example.com]
    observability:   # (7)!
      sentry: false
      prometheus: false
```

1. HTML 渲染后端 ID：`takumi`、`playwright`、第三方 Provider ID 或 `null`（不启用 HTML 渲染，仅保留模板转 HTML、资源与绘图能力）。
2. 启动策略：`off`（按需启动）、`warmup`（启动时初始化）、`probe`（启动并做最小探测）。当 `provider: null` 时必须保持 `off`。
3. 当前所选 `provider` 的专属配置，由对应后端负责校验。当 `provider: null` 时必须为空。
4. 跨所有 HTML 后端生效的输入、像素、体积与并发预算限制。
5. 独立的 Pillow / Skia 绘图配置，不依赖 `provider`。
6. 本地路径白名单、远程请求防护、缓存、模板与 Filehost 设置。
7. 可选的 Sentry 与 Prometheus 指标上报开关。

## 顶层配置项一览

| 配置键 | 默认值 | 详细文档 |
| --- | --- | --- |
| `provider` | `null` | [Takumi](takumi.md) · [Playwright](playwright.md) |
| `startup` | `"off"` | 见下方 [启动策略与生命周期](#startup-lifecycle) |
| `provider_config` | `{}` | 由所选后端解析，不可在顶层混写后端专属键 |
| `html` | 见下方预算表 | 见下方 [HTML 渲染预算](#html-budget) |
| `graphics` | `backends: []` | [绘图后端配置（Pillow / Skia）](graphics.md) |
| `resources` | 默认拒绝本地与内网 | [资源访问、Filehost 与安全](resources-and-security.md) |
| `observability` | 全部关闭 | [可观测性与监控](resources-and-security.md#observability) |

## 环境变量与 `.env`

本插件**不会**自行读取 `.env` 文件，也没有专属的整棵配置树环境变量。环境变量的加载与插值完全由 Entari 负责。

推荐把远程浏览器地址、访问令牌、Filehost 密钥、Sentry DSN 等敏感值放到环境变量中，在 Entari 配置里引用：

```yaml
plugins:
  htmlrender:
    provider: playwright
    provider_config:
      connect_ws:
        endpoint: ${{ env.PLAYWRIGHT_WS_URL }}
```

## 启动策略与生命周期 { #startup-lifecycle }

`startup` 决定了 HTML 渲染引擎在 Entari 启动阶段（Launart `preparing`）的行为：

| 策略 | 启动阶段行为 | 适用场景 |
| --- | --- | --- |
| `off`（默认） | 不启动引擎，等到第一次收到渲染请求时再按需初始化 | 仅使用模板/绘图，或开发期想加快机器人启动速度 |
| `warmup` | 启动阶段直接初始化渲染引擎（如连接远程浏览器或加载字体） | 希望降低第一次渲染的冷启动延迟 |
| `probe`（生产推荐） | 启动阶段完成初始化，并执行一次最小可用性探测 | 生产环境提前暴露版本不匹配、网络不通或字体缺失问题 |

!!! note "插件重载与关闭行为"
    - **关闭与重载**：进入 `cleanup` 阶段时，插件会先停止接收新请求，等待正在进行的渲染和租约自然结束，再依次关闭绘图、HTML 引擎、模板、资源与 Filehost。
    - **配置出错保护**：在 Entari 热重载中，配置解析、后端检查和绘图源码加载会先在暂存阶段完成，失败时不会破坏正在运行的旧实例。但一旦进入新实例的启动探测阶段失败，需要修复配置后手动再次重载插件。

## HTML 渲染预算 { #html-budget }

`html` 下的限制同时作用于 Takumi、Playwright 及第三方 HTML 后端，用于防止超大输入或超长页面拖垮服务：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `max_source_bytes` | `67108864` (64 MiB) | 单次输入 HTML / Markdown / 文本的最大字节数 |
| `max_pixels` | `16777216` (1600 万像素) | 输出图片的最大总像素数（宽 × 高） |
| `max_output_bytes` | `67108864` (64 MiB) | 输出图片编码后的最大字节数 |
| `max_device_pixel_ratio` | `4.0` | 允许传入的最大 `device_pixel_ratio` |
| `max_auto_height` | `16384` | `height=None` 自动撑开时的最大高度（像素） |
| `max_concurrency` | `2` | 允许同时执行的 HTML 渲染任务上限 |

参数本身非法时抛出 `InvalidRenderInputError`；实际渲染结果超过像素、高度或体积上限时抛出 `RenderOutputLimitError`（不会静默裁切图片）。
