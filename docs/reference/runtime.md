---
title: Runtime 与 Entari Service
description: caller services、advanced composition 与生命周期所有权
---

# Runtime 与 Entari Service

## 普通调用路径

Entari handler 通过 DI 接收 concrete `HtmlRenderService`。service 直接提供五个稳定入口：

| 属性 | 语义 |
| --- | --- |
| `renderer: HtmlRenderer` | HTML、文本、Markdown、模板或 `PreparedHtml` 到图像 |
| `templates: TemplateRenderer` | `TemplateRef` 到 `RenderedHtml` |
| `resources: ResourceAccess` | 显式 locator fetch 与 scoped publish |
| `graphics: GraphicsRenderer` | `RasterScene` 到图像，与 HTML Provider 独立 |
| `capabilities: RuntimeCapabilities` | Playwright、Takumi 与第三方的 typed capability |

```python
from entari_plugin_htmlrender import RasterOptions, RenderedImage
from entari_plugin_htmlrender.entari import HtmlRenderService

async def render_status(service: HtmlRenderService) -> RenderedImage:
    return await service.renderer.rasterize_html(
        "<strong>ready</strong>",
        raster=RasterOptions(width=640, device_pixel_ratio=1),
    )
```

框架无关函数应直接接收它真正需要的 `HtmlRenderer` / `TemplateRenderer` /
`ResourceAccess` / `GraphicsRenderer` contract；依赖解析只发生在 Entari DI 边界。

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

Entari 中不要手工驱动 service 内部 runtime。`HtmlRenderService` 没有公共`startup()` / `probe()` / `aclose()`；Launart stages 与插件热卸载拥有其生命周期。
