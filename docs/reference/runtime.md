---
title: Runtime 与 Entari Service
description: caller services、advanced composition 与生命周期所有权
---

# Runtime 与 Entari Service

## 普通调用路径

Entari handler 通过 DI 接收 concrete `HtmlRenderService`。service 直接提供六个稳定入口：

| 属性 | 语义 |
| --- | --- |
| `preparation: HtmlPreparer` | HTML、文本、Markdown 或模板到中立 `PreparedHtml` |
| `renderer: HtmlRenderer` | HTML、文本、Markdown、模板或 `PreparedHtml` 到图像 |
| `templates: TemplateRenderer` | `TemplateRef` 到 `RenderedHtml` |
| `resources: ResourceAccess` | 显式 locator fetch 与 scoped publish |
| `graphics: GraphicsRenderer` | `RasterScene` 到图像，与 HTML Provider 独立 |
| `capabilities: RuntimeCapabilities` | Playwright、Takumi 与第三方的 typed capability |

```python
from entari_plugin_htmlrender import RasterOptions, RenderedImage
from entari_plugin_htmlrender.entari import HtmlRenderService

async def render_status(service: HtmlRenderService) -> RenderedImage:
    prepared = await service.preparation.prepare_html("<strong>ready</strong>")
    return await service.renderer.rasterize_prepared(
        prepared,
        raster=RasterOptions(width=640, device_pixel_ratio=1),
    )
```

框架无关函数应直接接收它真正需要的 `HtmlPreparer`、`HtmlRenderer`、`TemplateRenderer`、`ResourceAccess` 或 `GraphicsRenderer` contract；依赖解析只发生在 Entari DI 边界。`service.preparation` 与 `service.renderer` 都属于当前 plugin lifetime，不能存入模块级单例。

Entari handler 也可以直接注入这些 contract，而不必先接收整个 service：

```python
from entari_plugin_htmlrender import HtmlPreparer

async def prepare_status(preparation: HtmlPreparer):
    return await preparation.prepare_html("<strong>ready</strong>")
```

插件加载时会把 `HtmlRenderer`、`TemplateRenderer`、`HtmlPreparer`、`ResourceAccess` 与 `GraphicsRenderer` 注册到 Letoderea DI。provider 从 Launart 当前 active service 解析 contract，因此已编译 handler 在插件 reload 后仍会取得新 service 的实例；插件 unload 时对应 provider 随 plugin scope 自动移除。

配置模型使用未绑定的 `plugin_config(HtmlRenderConfig)`。配置发生语义变化时，Entari 的 `ConfigReload` 默认路径会对插件执行 staged reload。导入、配置校验或 runtime composition 构建失败时，旧插件会继续运行。replacement promote 发生在 Launart service 进入 `preparing` 之前，因此 service startup/probe 失败不能回滚已经 promote 的插件；部署时应先用 `startup: off` 验证配置，或在升级时接受启动健康检查失败会使新 runtime 不可用这一边界。

## Advanced composition

`RenderRuntime` 是创建宿主管理的一次 composition aggregate。普通业务代码不需要它；框架适配器或独立 embedding 才显式构建并持有它：

```python
from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig

config = HtmlRenderConfig.model_validate({"provider": "playwright", "startup": "off"})
plan = build_runtime_plan(config)
runtime = plan.build_runtime()
server = plan.hosted_asset_server

try:
    if server is not None:
        await server.startup()
    await runtime.startup()
    image = await runtime.renderer.rasterize_html("<b>ready</b>")
finally:
    try:
        await runtime.aclose()
    finally:
        if server is not None:
            await server.aclose()
```

构建 plan/runtime 不执行外部 I/O。`RuntimePlan` 是 one-shot ownership value，`build_runtime()` 恰好调用一次；第二次调用抛出 `InvalidRenderInputError(operation="runtime.build", field="plan")`，需要另一个 runtime 时应重建 plan。Provider-owned parsed config 在 plan → availability →compose 期间保持同一 identity。若 resource strategy 需要 filehost，计划持有的 server与生成的唯一 runtime 同寿命：创建方先启动 `hosted_asset_server`，关闭时先排空runtime，再关闭 server。

测试或 embedding 若要绕过 entry-point discovery，可传配置所选的单个 Provider：

```python
plan = build_runtime_plan(config, provider_override=provider)
```

该参数不是候选列表；override 的 ID 必须与 `config.provider` 一致。

## Runtime 生命周期

- 初始状态为 `RuntimeState.OPEN`；`startup()` 幂等且并发安全。startup policy `off`只跳过 eager startup，首个已获准 Provider operation 可以 lazy acquire。
- `probe()` 先确保 startup 完成，再执行 Provider 的最小探测。
- `aclose()` 先切到 `CLOSING`，永久停止新操作，等待已接纳操作完成，再关闭Provider/resources；成功后进入 `CLOSED`。
- 排空或关闭被取消/失败时保持 `CLOSING`，后续 `aclose()` 可重试；runtime 不会重新开放。

Entari 中不要手工驱动 service 内部 runtime。`HtmlRenderService` 没有公共 `startup()` / `probe()` / `aclose()`；Launart stages 与插件热卸载拥有其生命周期。关闭开始后，`preparation`、`renderer`、`resources` 与 capability leases 都按同一 admission boundary 拒绝新工作并排空已接纳工作。
