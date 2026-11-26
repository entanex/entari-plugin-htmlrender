---
title: 浏览器操作与引擎专属能力
description: 使用 Playwright 操控网页与选择器截图、调用 Takumi 专属接口，以及多引擎组合切换
icon: lucide/sparkles
---

# 浏览器操作与引擎专属能力

`HtmlRenderer` 只提供所有 HTML 引擎都支持的通用出图接口。当你需要使用某个引擎独有的高级特性——比如用 Playwright 打开网页并截取某个元素，或者用 Takumi 生成 SVG、测量布局、输出动图——可以通过 `service.capabilities` 按租约借用对应能力。

!!! warning "租约生命周期规则"
    所有 `lease_*()` 方法返回的都是异步上下文管理器（`async with`）。借出的页面、浏览器、会话、编译结果或原生渲染器**只能在 `async with` 块内使用**，绝对不要带出块外或存进全局变量，否则会导致关闭插件时一直等待资源释放。

---

## Playwright：网页导航与选择器截图

当 `provider: playwright` 时，通过 `service.capabilities.playwright` 获取 `PlaywrightCapability`：

```python
from entari_plugin_htmlrender import RenderedImage
from entari_plugin_htmlrender.entari import HtmlRenderService


async def screenshot_element(service: HtmlRenderService, url: str) -> RenderedImage:
    pw = service.capabilities.playwright
    async with pw.lease_page(
        viewport={"width": 1280, "height": 720},
        extra_http_headers={"Accept-Language": "zh-CN"},
    ) as page:
        await page.goto(url, wait_until="networkidle")
        card = page.locator(".profile-card")
        raw_png = await card.screenshot(type="png")
        return RenderedImage.from_bytes(raw_png, expected_format="png")
```

- `lease_page(**options)`：借用一个受托管的原生 Playwright `Page`，退出 `async with` 时自动关闭回收。
- `lease_browser()`：需要自行管理多个 Context 或复杂会话时，可直接借用原生 `Browser`。

!!! danger "原生租约的安全责任"
    通过 `lease_page()` / `lease_browser()` 直接操作浏览器时，插件**不会**替你拦截页面跳转或校验目标地址，原生 Playwright 异常也会原样抛出。如果你要访问用户提供的 URL，请务必自行做好域名、IP 与重定向白名单校验。

---

## Takumi：SVG、布局测量、动图与动态字体

当 `provider: takumi` 时，通过 `service.capabilities.takumi` 获取 `TakumiCapability`，提供三个层次的租约接口：

=== "TakumiSession（常用会话）"

    适合输出 SVG、动态注册本地字体文件以及查看编译缓存统计：

    ```python
    from pathlib import Path
    from entari_plugin_htmlrender.entari import HtmlRenderService


    async def render_svg(service: HtmlRenderService) -> str:
        async with service.capabilities.takumi.lease_session() as session:
            # 查看编译缓存命中统计
            stats = session.compiled_cache_stats
            # 直接将 HTML 转为 SVG 字符串
            return await session.render_svg_html("<div style='color:blue'>Hi</div>")
    ```

    `TakumiSession` 还提供 `register_font_file(..., unicode_range=...)` 和 `registered_font_families`。

=== "TakumiAPI（完整托管接口）"

    提供编译复用、布局测量、动图帧编码与动态字体缓存：

    - **编译复用**：`compile_html(...)` 返回绑定当前租约的 `TakumiCompiledDocument`，可多次测量或渲染。
    - **布局测量**：获取元素实际排版尺寸。
    - **动图与帧编码**：支持输出 WebP、APNG（帧率上限 **90 FPS**）与 GIF（帧率上限 **50 FPS**）；超限会转为 `ProviderExecutionError`。
    - **动态字体缓存**：`cache_font(font, key)`、`cached_fonts(key, pin=False)`、`unregister_font(name)`、`clear_fonts()`。

=== "原生 Renderer（高级）"

    需要直接调用 `takumi_py.Renderer` 底层接口时，可使用 `async with service.capabilities.takumi.lease_native_renderer() as native:`。注意原生对象为同步接口，调用方需自行管理线程阻塞与异常。

---

## 多引擎组合与运行时切换

### 同时启用多个绘图后端

你可以在配置中同时启用 Pillow 和 Skia，并按需在业务中选择使用哪一个：

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    graphics:
      backends: [pillow, skia] # 首项 pillow 作为 service.graphics 的默认实现
      drawings:
        avatar_grid:
          backend: pillow
          path: drawings/avatar_grid.py
        vector_badge:
          backend: skia
          path: drawings/vector_badge.py
```

在代码中，你可以：

- 用 `service.graphics` 调用默认绘图后端（此处为 Pillow）渲染 `RasterScene`。
- 用 `service.capabilities.pillow` 或 `service.capabilities.skia` 显式指定某个后端。
- 用 `service.drawings.render("avatar_grid", ...)` 或 `render("vector_badge", ...)` 调用各自绑定的绘图函数。

### 运行时安全探测可用能力

如果你的业务插件希望兼容不同用户的配置（有的用户装了 Takumi，有的装了 Playwright），可以先探测再分支，避免直接触发 `CapabilityUnavailableError`：

```python
from entari_plugin_htmlrender import RenderOperation
from entari_plugin_htmlrender.entari import HtmlRenderService


async def smart_render(service: HtmlRenderService):
    # 检查当前 HTML 渲染器是否支持某项操作
    if service.renderer.supports(RenderOperation.RASTERIZE_MARKDOWN):
        ...

    # 检查某个专属能力是否已启用
    if "playwright" in service.capabilities.available_names:
        pw = service.capabilities.playwright
        ...
```
