# entari-plugin-htmlrender

把 HTML、Markdown 和 Jinja2 模板渲染成图片的 Entari 插件。支持 Playwright、Takumi，也提供 Pillow 和 Skia 绘图接口。

## 安装

需要 Python `>=3.11,<4.0`、Entari `>=0.19.4,<0.20.0`。

一般使用 Playwright，安装后还需要下载浏览器：

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.2.0,<0.3"
uv run playwright install chromium
```

在 Debian / Ubuntu 或基于它们的容器中，可以用 `uv run playwright install --with-deps chromium` 一并安装系统依赖。

如果使用 Takumi：

```bash
uv add "entari-plugin-htmlrender[takumi]>=0.2.0,<0.3"
```

Pillow、Skia 按需安装，对应的可选依赖是 `pillow`、`skia`。只安装基础包不会安装渲染后端。

## 配置

在 Entari 配置中启用 `htmlrender`：

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
```

`startup: probe` 会在启动时检查后端是否可用。使用 Takumi 时，将 `provider` 改为 `takumi`，并移除 Playwright 专用的 `provider_config`。

## 使用

在 Entari 事件处理函数的参数中声明 `renderer: HtmlRenderer`，即可取得渲染接口。下面是一个生成 Markdown 图片的例子，省略了事件注册部分：

```python
from entari_plugin_htmlrender import HtmlRenderer, RasterOptions, RenderedImage


async def build_card(renderer: HtmlRenderer) -> RenderedImage:
    return await renderer.rasterize_markdown(
        "# Hello, Entari\n\n这是一张用 Markdown 生成的图片。",
        raster=RasterOptions(width=720),
    )
```

返回值是 `RenderedImage`，用 `bytes(image)` 获取图片数据，再交给消息发送接口。

HTML、纯文本和模板分别使用 `rasterize_html()`、`rasterize_text()`、`rasterize_template()`，参数和示例见[渲染内容](docs/guides/rendering-content.md)。

本地模板、图片和字体的读取路径需要加入 `resources.local_access.allowed_paths`，配置方式见[模板与资源](docs/guides/templates-and-resources.md)。插件负责启动和关闭后端；不要把注入的对象长期保存在全局变量中，热重载后它们会被替换。

## 后端与限制

- **Playwright**：使用浏览器排版，支持 JavaScript、Markdown 公式和网页截图，也可以连接远程浏览器。需要安装浏览器及其系统依赖。
- **Takumi**：不需要浏览器，适合静态内容渲染。HTML、CSS 的支持范围有限，不执行 JavaScript，也不支持网页导航和 CSS 选择器截图。中文等字符需要额外配置字体；安装时也要留意 `takumi-py` 对目标平台的支持。
- **Pillow / Skia**：用 Python 函数绘图，支持按名称加载 `.py` 文件或模块。在 Entari 中由插件系统管理模块引用和可选热重载，也保留 `RasterScene` 场景接口。不解析 HTML 或 Markdown，配置见[Python 绘图](docs/configuration/graphics/index.md)。

### 数学公式

Markdown 公式通过 KaTeX 渲染，目前需要选择 **Playwright**。行内公式可写为 `$x$` 或 `\(x\)`；块级公式使用独占段落的 `$$...$$` 或 `\[...\]`。`$ x $` 会保留为普通文本。

**Takumi 目前不能直接渲染 Markdown 数学公式。** 这条渲染流程依赖 JavaScript，使用 Takumi 渲染含公式的 Markdown 会抛出 `UnsupportedDocumentFeatureError`。插件尚未提供将公式自动转换成静态 SVG 或图片的功能。

其他差异见[后端选择](docs/start/choosing-provider.md)，Takumi 的详细说明见 [Takumi 配置](docs/configuration/providers/takumi.md)。

## 文档与示例

- [完整文档](https://entanex.github.io/entari-plugin-htmlrender/)
- [从 0.1 升级到 0.2](docs/start/migration-v0.2.md)
- [本地模板渲染](examples/template_render)
- [连接远程浏览器](examples/remote_browser)
- [Takumi 高级接口](examples/takumi_capability)
- [Pillow / Skia 绘图](examples/graphics_render)
- [编写第三方渲染后端](examples/echo-provider)

## License

[MIT](LICENSE)
