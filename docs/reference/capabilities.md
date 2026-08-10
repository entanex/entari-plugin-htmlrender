---
title: Capability 参考
description: Playwright、Takumi、Pillow、Skia 与第三方 typed extensions
---

# Capability 参考

`RenderRuntime.extensions` 暴露无法放入通用 `HtmlRenderer` 的 Provider/adapter 专属语义。第一方属性为 `.playwright`、`.takumi`、`.pillow`、`.skia`；第三方扩展使用`get(key)` / `require(key)`。

## Playwright

```python
from entari_plugin_htmlrender import RuntimeSource, resolve_runtime

async def screenshot(runtime: RuntimeSource, url: str) -> bytes:
    access = resolve_runtime(runtime).extensions.playwright
    async with access.page() as page:
        await page.goto(url)
        return await page.screenshot(type="png")
```

`page(**browser_new_page_options)` 与 `browser()` 返回异步上下文管理器，内部对象是Playwright 原生类型。原生异常不会翻译为通用 rendering error。

## Takumi

```python
from entari_plugin_htmlrender import RuntimeSource, resolve_runtime

async def render_svg(runtime: RuntimeSource) -> str:
    access = resolve_runtime(runtime).extensions.takumi
    async with access.api() as api:
        return await api.render_svg_html("<main>vector</main>", width=640)
```

`api()` 暴露受管理的 compile/render/measure/SVG/animation/font 操作；`renderer()`租用原生 `takumi_py.Renderer`，调用方自行承担 worker、参数验证与 native 错误边界。

### TakumiAPI 方法矩阵

<!-- takumi:compile -->

| 分组 | 方法 |
| --- | --- |
| Compile | `compile_html`、`compile_node`、`compile_stylesheet`、`compile_keyframes` |

<!-- takumi:raster -->

| 分组 | 方法 |
| --- | --- |
| Raster | `render_html`、`render_compiled`、`render_node` |

<!-- takumi:measure -->

| 分组 | 方法 |
| --- | --- |
| Measure | `measure_html`、`measure_compiled`、`measure_node` |

<!-- takumi:svg -->

| 分组 | 方法 |
| --- | --- |
| SVG | `render_svg_html`、`render_svg_compiled`、`render_svg_node` |

<!-- takumi:animation -->

| 分组 | 方法 |
| --- | --- |
| Animation | `render_animation`、`render_sequence_at_time`、`encode_frames` |

<!-- takumi:font -->

| 分组 | 方法 |
| --- | --- |
| Font | `register_font`、`register_fonts`、`register_font_file` |

只读属性为 `registered_font_families` 与 `compiled_cache_stats`。每个受管理方法都有稳定的 `takumi.api.*` telemetry 名称；`render_sequence_at_time` 保留既有的`takumi.api.render_sequence` operation。

## Pillow 与 Skia

两者实现 `RasterSceneRenderer.render(RenderRasterSceneRequest) -> RenderedImage`。通过 `graphics.backends` 显式启用；它们不消费 `PreparedHtml` 或 `provider_config`。

## 租约规则

任何 raw Page、Browser、Takumi API/renderer 都只能在当前上下文内使用。runtime
cleanup 会等待活跃租约；离开上下文或热卸载后必须丢弃对象。
