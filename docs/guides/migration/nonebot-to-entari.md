---
title: 从 NoneBot 版本迁移到 Entari
description: 包名、配置、公共 API、生命周期和可选集成的完整迁移清单
---

# 从 NoneBot 版本迁移到 Entari

这次迁移不是兼容层：包、宿主生命周期与公共 API 已按 Entari 的服务模型重新建立。迁移后应删除旧包与旧插件配置，不要在两个框架间共享 runtime。

## 对照表

| 旧契约 | Entari 契约 | 迁移动作 |
| --- | --- | --- |
| distribution `nonebot-plugin-htmlrender` | `entari-plugin-htmlrender` | 用 `uv remove`/`uv add` 替换依赖；Python 与基础依赖版本约束不变 |
| import `nonebot_plugin_htmlrender` | `entari_plugin_htmlrender` | 更新所有 import 与类型引用 |
| NoneBot 插件配置中的 `render.*` wrapper | Entari `plugins.htmlrender` 下的直接键 | `render.provider` 变为 `provider`，其余 `startup`、`provider_config`、`html`、`graphics`、`resources`、`observability` 同理 |
| `RenderPluginConfig` | `RenderSettings` | 删除宿主 wrapper 类型；Entari metadata 直接使用 `RenderSettings` 校验插件配置 |
| `Application` | `RenderRuntime` | 把一次组合生命周期的显式聚合对象改名并收口到 runtime 语义 |
| `Renderer` | `HtmlRenderer` | typed request 通过 `runtime.renderer` 执行；能力探测改用 `RenderCommand` |
| `ApplicationLifecycle` | `RuntimeLifecycle` | Provider 生命周期协议改用 runtime 词汇；宿主所有权由 `HtmlRenderService` 承担 |
| `ApplicationNotInitialized` | `RuntimeNotBound` | 未传显式 runtime 且当前 task 未绑定时匹配新错误类型 |
| `prepare_html(...)` | `parse_html(...)` | 该操作仍是同步、纯解析；需要 I/O 的 preparation 函数保持异步 |
| `to_resource_url(...)` | `resolve_resource_url(...)` | 新函数是异步函数，并返回携带 URL 精确授权头的 `ResourceResolution[str]` |
| `get_default_application()`、`set_default_application(...)`、`get_default_renderer()`、默认 factory | 显式 `runtime=` 或 `runtime_context(...)` | 删除所有进程全局 setter/factory；Entari handler 由 DI 注入 `HtmlRenderService`；renderer 从 `resolve_runtime(...).renderer` 获取 |
| 顶层 `CapabilityCatalog` / `CapabilityKey` | `entari_plugin_htmlrender.rendering` 下的 Provider 扩展契约 | 普通调用者使用 `RenderCommand`；仅 Provider 作者操作 capability catalog |
| 顶层 `ResourceResolutionError` | 顶层 `ResourceResolutionError` | 类型保持稳定；它也可从 `entari_plugin_htmlrender.rendering` 或 `.resources` 导入 |
| Provider entry-point group `nonebot_plugin_htmlrender.providers` | `entari_plugin_htmlrender.providers` | 更新 distribution 的 entry point；entry 名必须等于 Provider ID |
| HTMLKit Provider/extra | 已移除 | 选择 Playwright、Takumi 或第三方 Provider；不要保留 `htmlkit` 配置 |
| 通过 `nonebot-plugin-sentry` / Prometheus 插件接线 | 直接使用 `sentry-sdk` / `prometheus-client` | 安装 `sentry` / `prometheus` extra，并设置 `observability` 开关；SDK 初始化与 exporter registry 仍由应用部署负责 |
| 依赖 NoneBot ASGI/FastAPI 暴露 filehost | 插件显式拥有 aiohttp `HostedAssetHttpServer` | 安装 `filehost` extra；配置外部可达的 `resources.filehost.public_base_url` 和独立 bind 地址 |

## 配置迁移

旧配置：

```yaml
render:
  provider: playwright
  startup: probe
  resources:
    local_access:
      allowed_paths: [assets]
```

Entari 配置：

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    resources:
      local_access:
        allowed_paths: [assets]
```

`RenderSettings` 禁止未知键，拼写错误会在插件配置阶段失败。

## 调用迁移

Entari handler 让 DI 注入 `HtmlRenderService`，然后显式传递 service：

```python
from entari_plugin_htmlrender import render_markdown
from entari_plugin_htmlrender.host import HtmlRenderService

async def render_help(service: HtmlRenderService) -> bytes:
    image = await render_markdown("# Help", runtime=service)
    return bytes(image)
```

框架无关函数接受 `RuntimeSource`。同一任务中调用很多函数时可进入`runtime_context(source)`；该绑定只随当前 task/child task 传播，不是进程默认值。

## 生命周期迁移

Entari loader 调用 `add_service` 注册 `HtmlRenderService`。Launart 在`preparing` 阶段启动 filehost 并按 `off` / `warmup` / `probe` 准备 Provider，`blocking` 阶段等待退出信号，`cleanup` 阶段拒绝新操作、drain 在途操作并关闭runtime/filehost。插件热卸载也走 cleanup。不要在业务 handler 中手工重建或替换service 持有的 runtime。
