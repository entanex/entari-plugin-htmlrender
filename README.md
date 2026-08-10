# entari-plugin-htmlrender

Entari 的 provider-neutral HTML、Markdown、模板与栅格场景渲染库。

它把宿主生命周期、渲染用例和引擎 adapter 分开：Entari 拥有一个`HtmlRenderService`，服务解析出 `RenderRuntime`；业务代码通过 caller-first API显式传入 `runtime=`，不会读取进程级默认对象。

## 安装

Python 版本要求保持为 `>=3.10,<4.0`。按实际能力选择 extra：

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.8.0,<0.9"
# 或：takumi / pillow / skia / filehost / sentry / prometheus
```

Entari 配置中的插件短名为 `htmlrender`，字段直接对应 `RenderSettings`：

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
```

`provider` 可为 `playwright`、`takumi`、第三方 Provider ID 或 `null`；Pillow 与Skia 是独立 Graphics capability，通过 `graphics.backends` 启用。

## 常用 API

在 Entari handler 中让 DI 注入 `HtmlRenderService`，然后显式传给渲染函数：

```python
from entari_plugin_htmlrender import (
    RenderedImage,
    parse_html,
    render_markdown,
    resolve_resource_url,
)
from entari_plugin_htmlrender.host import HtmlRenderService


async def build_card(service: HtmlRenderService) -> tuple[RenderedImage, str]:
    prepared = parse_html("<main>Hello</main>")
    image = await render_markdown("# Hello, Entari", width=720, runtime=service)
    resource = await resolve_resource_url(
        b"inline asset",
        runtime=service,
    )
    assert prepared.html
    return image, resource.value
```

`HtmlRenderService` 结构化实现 `RuntimeResolver`。在框架无关的函数中，也可以直接接收 `RuntimeSource`：

```python
from entari_plugin_htmlrender import RuntimeSource, render_html, resolve_runtime


async def render_badge(runtime: RuntimeSource) -> bytes:
    active = resolve_runtime(runtime)
    image = await render_html("<b>ready</b>", runtime=active)
    return bytes(image)
```

需要 typed request 或能力发现时，使用 `RenderRuntime.renderer` 上的`HtmlRenderer`；需要原生 Playwright、Takumi 或 Graphics 操作时，从`RenderRuntime.extensions` 租用相应 capability。

## 生命周期

插件加载时通过 Entari `add_service` 注册 `HtmlRenderService`。Launart 的`preparing` 阶段启动显式 filehost 并按 `startup` 策略启动/探测 Provider，`blocking` 阶段等待退出信号，`cleanup` 阶段停止接收新操作、等待在途操作完成并关闭 runtime 与 filehost。插件热卸载同样进入 cleanup；关闭操作幂等，失败可重试。

## 文档与示例

- [完整文档](https://kexue-z.github.io/entari-plugin-htmlrender/)
- [`examples/template_render`](examples/template_render)：Entari DI 与模板渲染
- [`examples/remote_browser`](examples/remote_browser)：远程 Playwright
- [`examples/takumi_capability`](examples/takumi_capability)：Takumi typed capability
- [`examples/graphics_render`](examples/graphics_render)：Pillow/Skia `RasterScene`
- [`examples/echo-provider`](examples/echo-provider)：第三方 Provider entry point

## License

项目使用 MIT License。启用第三方 Provider 或 native backend 前，请同时检查其依赖与分发许可。
