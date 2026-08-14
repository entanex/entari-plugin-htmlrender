---
title: Capability 参考
description: RuntimeCapabilities、Playwright、Takumi 与第三方 typed capability
---

# Capability 参考

`HtmlRenderService.capabilities` 暴露无法放入通用 `HtmlRenderer` 的 Provider 专属语义。第一方属性为 `.playwright` 与 `.takumi`；第三方 capability 使用 typed
`CapabilityKey` 配合 `get()` / `require()`。可用名称由只读`available_names` 返回。

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

需要尚未进入稳定 managed API 的上游对象时，可显式使用`lease_native_renderer()`。返回值类型刻意为 `object`；调用方选择这一逃生口后自行承担 native typing、线程/worker 与底层错误语义。

## 第三方 capability

```python
from entari_plugin_htmlrender.rendering import CapabilityKey
from entari_plugin_htmlrender.runtime import RuntimeCapabilities

METRICS = CapabilityKey("acme.metrics", MetricsCapability)

def optional_metrics(capabilities: RuntimeCapabilities):
    return capabilities.get(METRICS)
```

名称必须是稳定的小写标识，interface 必须是 `@runtime_checkable` protocol。`require()` 在缺失时抛出 `CapabilityUnavailableError`；`get()` 的 `None` 只表示正常缺失。

## Graphics 不属于 capability

Pillow/Skia 实现独立的 `GraphicsRenderer`，由 `HtmlRenderService.graphics` 暴露。业务代码不通过 capability catalog 选择 backend；详见[RasterScene 指南](../guides/raster-scenes.md)。

## 租约规则

任何 Page、Browser、Takumi session/native renderer 都只能在当前 async context 内使用。runtime cleanup 会等待活跃租约；离开上下文或插件热卸载后必须丢弃对象。
