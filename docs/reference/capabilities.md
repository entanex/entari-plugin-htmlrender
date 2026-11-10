---
title: Capability 参考
description: RuntimeCapabilities、Playwright、Takumi 与第三方 typed capability
---

# Capability 参考

`HtmlRenderService.capabilities` 暴露无法放入通用 `HtmlRenderer` 的 Provider 专属与独立图形语义。第一方属性为 `.playwright`、`.takumi`、`.pillow` 与 `.skia`；第三方 capability 使用 typed `CapabilityKey` 配合 `get()` / `require()`。可用名称由只读 `available_names` 返回。

普通 HTML rasterization 不需要 capability。框架无关函数若确实使用专属行为，应直接依赖对应 protocol，而不是接收整个 service。

## Playwright

```python
from entari_plugin_htmlrender.capabilities import PlaywrightCapability

async def screenshot(
    playwright: PlaywrightCapability,
    url: str,
) -> bytes:
    async with playwright.lease_page(viewport={"width": 1280, "height": 800}) as page:
        await page.goto(url)
        return await page.screenshot(type="png")
```

`lease_page(**options)` 与 `lease_browser()` 返回 async context manager。原生 Page或 Browser 只能在上下文内使用；URL 导航的 scheme/host/egress 策略由调用层负责。

## Takumi

```python
from entari_plugin_htmlrender.capabilities import TakumiCapability

async def render_svg(takumi: TakumiCapability) -> str:
    async with takumi.lease_session() as session:
        return await session.render_svg_html(
            "<main>vector</main>",
            width=640,
        )
```

受管理的 `TakumiSession` 提供 HTML raster、`render_svg_html()`、`register_font_file()`，以及只读的 `registered_font_families` 与`compiled_cache_stats`。这些操作在 runtime admission、lease 与稳定错误边界内。

高级调用通过 `lease_api()` 获得 `TakumiAPI`，覆盖以下操作：

| 类别 | 方法 |
| --- | --- |
| 编译 | `compile_html`、`compile_node`、`compile_stylesheet`、`compile_keyframes` |
| 位图 | `render_html`、`render_compiled`、`render_node` |
| 测量 | `measure_html`、`measure_compiled`、`measure_node` |
| SVG | `render_svg_html`、`render_svg_compiled`、`render_svg_node` |
| 动画与帧 | `render_animation`、`render_sequence_at_time`、`encode_frames` |
| 字体 | `register_font`、`register_fonts`、`register_font_file` |

```python
from entari_plugin_htmlrender.capabilities import TakumiCapability

async def compile_card(takumi: TakumiCapability) -> bytes:
    async with takumi.lease_api() as api:
        document = await api.compile_html("<main>Compiled card</main>")
        await api.measure_compiled(document, width=640)
        return await api.render_compiled(document, width=640)
```

`TakumiCompiledDocument` 绑定创建它的 runtime 与当前 lease，不能传给另一个 runtime 或留到下次 lease 使用。高级调用和小型 session 都会在 lease 退出后失效，已生成的图像字节、SVG 字符串和统计快照可以保留。

需要直接操作上游对象时，可显式使用`lease_native_renderer()`。安装对应 extra 后，`lease_page()`、`lease_browser()` 与 `lease_native_renderer()` 分别保留上游 `Page`、`Browser`、`takumi_py.Renderer` 类型，IDE 无需 `cast` 即可补全。native renderer 调用方仍承担同步执行、线程/worker 与底层错误语义；普通库导入不会加载这些可选引擎。

## 第三方 capability

```python
from entari_plugin_htmlrender.rendering import CapabilityKey
from entari_plugin_htmlrender.runtime import RuntimeCapabilities

METRICS = CapabilityKey("acme.metrics", MetricsCapability)

def optional_metrics(capabilities: RuntimeCapabilities):
    return capabilities.get(METRICS)
```

名称必须是稳定的小写标识，interface 必须是 `@runtime_checkable` protocol。`require()` 在缺失时抛出 `CapabilityUnavailableError`；`get()` 的 `None` 只表示正常缺失。

## Graphics

Pillow 与 Skia 消费相同的 `RasterScene` 和 `RasterEncodeOptions`，并分别通过 `runtime.capabilities.pillow` 与 `runtime.capabilities.skia` 暴露为 `GraphicsRenderer`。`HtmlRenderService.graphics` 仍是兼容主入口，指向 `graphics.backend`，或在未设置该字段时指向 `graphics.backends` 的第一项。

```yaml
graphics:
  backends: [pillow, skia]
```

两个 backend 可在一个 runtime 中同时可用。它们共享 runtime admission、worker 与操作观察器，但各自拥有独立 `RasterWorkBudget`，每个 backend 独立执行像素、命令和并发限制；多 backend 的总并发上限为各自上限之和。

配置为可用的 backend 使用稳定 typed key `PILLOW_RASTER_SCENE_RENDERER` / `SKIA_RASTER_SCENE_RENDERER`。若依赖未安装，主入口仍在首次调用时以 `GraphicsBackendUnavailableError` 给出安装诊断；不可用的次级 backend 不进入 catalog，对应属性抛出 `CapabilityUnavailableError`，不会静默回退到另一个实现。完整选择规则见 [Graphics 后端](../configuration/graphics/index.md)。

## 租约规则

任何 Page、Browser、Takumi session/native renderer 都只能在当前 async context 内使用。runtime cleanup 会等待活跃租约；离开上下文或插件热卸载后必须丢弃对象。
