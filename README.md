# entari-plugin-htmlrender

Entari 的图片渲染插件，支持 HTML、Markdown、纯文本和 Jinja2 模板。

> [!NOTE]
> **Takumi 原生渲染**：在进程内完成排版和图片输出，无需安装浏览器，支持 SVG、布局测量和动画。另提供远程 Playwright 的网页截图与 JavaScript 支持，以及 Pillow / Skia 的 Python 绘图接口。

[使用文档](https://entanex.github.io/entari-plugin-htmlrender/) · [示例](examples) · [升级指南](docs/start/migration-v0.2.md)

## 快速开始

需要 Python `>=3.11,<4.0` 和 Entari `>=0.19.4,<0.20.0`。

```bash
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"
```

在 Entari 配置中启用插件：

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
```

在事件处理函数中注入 `HtmlRenderer`，即可调用渲染接口。下面省略事件注册，只展示图片生成部分：

```python
from entari_plugin_htmlrender import HtmlRenderer, RasterOptions, RenderedImage


async def render_card(renderer: HtmlRenderer) -> RenderedImage:
    return await renderer.rasterize_markdown(
        "# Hello, Entari\n\nRendered with Takumi.",
        raster=RasterOptions(width=720),
    )
```

返回值是 `RenderedImage`，通过 `bytes(image)` 获取图片数据。HTML、纯文本和模板分别使用 `rasterize_html()`、`rasterize_text()` 和 `rasterize_template()`。

渲染中文前，请先[配置字体](docs/configuration/providers/takumi.md)。读取本地模板、图片或字体时，需要将对应目录加入[路径白名单](docs/guides/templates-and-resources.md)。

## 渲染后端

| 后端 | 用途 |
| --- | --- |
| [Takumi](docs/configuration/providers/takumi.md) | 静态内容转图片；支持 SVG、布局测量、动画和字体管理 |
| [Playwright](docs/configuration/remote-playwright.md) | 连接远程浏览器，处理 JavaScript、网页截图和 Markdown 数学公式 |
| [Pillow / Skia](docs/configuration/graphics/index.md) | 使用 Python 函数绘图，支持加载文件或模块、模块间引用和可选热重载 |

Takumi 的 HTML/CSS 支持范围与浏览器不同，不执行 JavaScript，**目前不支持本插件的 Markdown 数学公式渲染**。样式、图片和字体的接入方式见 [Takumi 文档](docs/configuration/providers/takumi.md)。

> 本插件将在不久的将来弃用 Playwright 本地浏览器的安装、管理与启动，仅保留远程支持。当前版本仍可使用本地模式。远程连接仍需安装 `[playwright]`，但 Bot 环境无需执行 `playwright install`。迁移方式见[远程部署](docs/configuration/remote-playwright.md)。

## 示例

- [Jinja2 模板](examples/template_render)
- [Takumi SVG 与字体接口](examples/takumi_capability)
- [远程浏览器](examples/remote_browser)
- [Pillow / Skia 绘图](examples/graphics_render)

## License

[MIT](LICENSE)
