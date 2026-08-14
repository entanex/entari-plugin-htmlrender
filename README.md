# entari-plugin-htmlrender

Entari 的 provider-neutral HTML、Markdown、模板与栅格场景渲染库。

普通调用收口为四个显式 contract：`HtmlRenderer` rasterize 内容，`TemplateRenderer` render 模板 HTML，`ResourceAccess` fetch/publish 资源，`GraphicsRenderer` rasterize `RasterScene`。Entari 只负责组合并拥有 `HtmlRenderService` 的生命周期；业务代码不查找默认 runtime。

## 安装

Python 版本要求保持为 `>=3.10,<4.0`。按实际能力选择 extra：

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.1.0,<0.2"
uv run playwright install chromium
# 或选择：takumi / pillow / skia / filehost / sentry / prometheus
```

Entari 配置中的插件短名为 `htmlrender`，字段直接对应 `HtmlRenderConfig`：

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
    graphics:
      backend: pillow
```

`provider` 可为 `playwright`、`takumi`、第三方 Provider ID 或 `null`。Pillow/Skia 实现独立的 Graphics contract，不属于 HTML Provider。

## 常用 API

在 Entari handler 中让 DI 注入 concrete `HtmlRenderService`：

```python
from entari_plugin_htmlrender import (
    RasterOptions,
    RenderedImage,
)
from entari_plugin_htmlrender.entari import HtmlRenderService


async def build_card(service: HtmlRenderService) -> RenderedImage:
    return await service.renderer.rasterize_markdown(
        "# Hello, Entari",
        raster=RasterOptions(width=720),
    )
```

框架无关的业务函数应进一步收窄为它真正需要的 contract：

```python
from entari_plugin_htmlrender import HtmlRenderer, RenderedImage


async def render_badge(renderer: HtmlRenderer) -> RenderedImage:
    return await renderer.rasterize_html("<b>ready</b>")
```

`HtmlRenderService` 直接暴露 `.renderer`、`.templates`、`.resources`、`.graphics` 与 `.capabilities`。Playwright/Takumi 原生对象只通过`service.capabilities` 的显式 lease 使用；Pillow/Skia 的选择留在配置中，调用方始终使用 `service.graphics`。

## 生命周期

插件通过 Entari `add_service` 注册 `HtmlRenderService`。Launart 在 `preparing`阶段启动所需 filehost 并按 `startup` 策略启动/探测 Provider；在 `cleanup` 阶段停止接纳新操作、排空在途操作、关闭 runtime，最后关闭 filehost。热卸载复用同一边界，业务代码不调用 service 的内部启动或关闭方法。

## 文档与示例

- [完整文档](https://entanex.github.io/entari-plugin-htmlrender/)
- [`examples/template_render`](examples/template_render)：Entari DI 与模板 rasterization
- [`examples/remote_browser`](examples/remote_browser)：远程 Playwright capability
- [`examples/takumi_capability`](examples/takumi_capability)：Takumi managed session
- [`examples/graphics_render`](examples/graphics_render)：`GraphicsRenderer` 与 `RasterScene`
- [`examples/echo-provider`](examples/echo-provider)：第三方 Provider v2 entry point

## License

项目使用 MIT License。启用第三方 Provider 或 native backend 前，请同时检查其依赖与分发许可。
