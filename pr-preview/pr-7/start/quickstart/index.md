# 快速开始

本页带你用最轻量的方式跑通第一次渲染：使用 **Takumi** 引擎将 Markdown 转为图片，全程无需安装浏览器。

> [!NOTE]
>
> **环境要求**
>
> - **Python**：`>=3.11, <4.0`
> - **Entari**：`>=0.19.4, <0.20.0`

## 第一步：安装插件

`entari-plugin-htmlrender` 基础包不包含任何渲染后端，需要按场景安装对应的可选依赖：

适合绝大多数静态卡片、帮助菜单、Markdown 和 Jinja2 模板渲染：

```bash
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"
```

主流 Linux / macOS / Windows 平台均提供预编译包，无需安装 Rust 工具链。详情见 [Takumi 平台要求](<https://entanex.github.io/entari-plugin-htmlrender/pr-preview/pr-7/configuration/takumi/index.md#platform-requirements>)。

需要执行 JavaScript、截取外部网页或渲染 Markdown 数学公式时使用：

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.2.0"
```

- **远程模式（推荐）**：只需安装上述 Python 客户端，浏览器由独立服务提供，无需在机器人宿主机下载浏览器。
- **本地模式**：还需执行 `uv run playwright install --with-deps chromium` 安装浏览器二进制文件。

如果只需要用 Python 代码直接绘图，无需配置任何 HTML 引擎：

```bash
# 选择 Pillow（通用、零系统库依赖）
uv add "entari-plugin-htmlrender[pillow]>=0.2.0"

# 或选择 Skia（高性能矢量绘图）
uv add "entari-plugin-htmlrender[skia]>=0.2.0"
```

多个可选依赖可以用逗号组合在一起：

```bash
uv add "entari-plugin-htmlrender[takumi,pillow]>=0.2.0"
```

## 第二步：配置 Entari

在你的 Entari 配置文件中启用 `htmlrender` 插件：

```yaml
plugins:
  htmlrender:
    provider: takumi # (1)!
    startup: probe   # (2)!
```

1. 指定 HTML 渲染后端。可填 `takumi`、`playwright`，如果只需要模板转 HTML、资源读取或 Python 绘图，可以设为 `null`。
2. `probe` 会在 Entari 启动阶段初始化引擎并做一次最小可用性检查，配置出错时能第一时间发现。若希望首次调用时再启动，可设为 `off`（默认值）。

> [!TIP]
>
> **渲染中文需要配置字体**
>
> Takumi 默认内置的字体主要面向拉丁字符，直接渲染中文可能会出现缺字或方块。跑通下面的英文示例后，请参考 [Takumi 字体配置](<https://entanex.github.io/entari-plugin-htmlrender/pr-preview/pr-7/configuration/takumi/index.md#fonts>) 加载中文字体。

## 第三步：在代码中渲染图片

在你的 Entari 事件处理函数中，直接通过依赖注入接收 `HtmlRenderer`（或接收 `HtmlRenderService` 获取全部能力）：

```python
from entari_plugin_htmlrender import HtmlRenderer, RasterOptions, RenderedImage

async def render_help(renderer: HtmlRenderer) -> RenderedImage:
    return await renderer.rasterize_markdown(
        "# Hello, Entari\n\nRendered by htmlrender.",
        raster=RasterOptions(width=720),  # (1)!
    )
```

1. `RasterOptions` 控制输出宽度、高度、缩放倍率（默认 `device_pixel_ratio=2.0`）和图片格式（默认 PNG）。高度省略时会自动按内容高度撑开。

如果同一个函数里需要用到多个能力（例如同时使用模板、资源和绘图），可以注入 `HtmlRenderService`：

```python
from entari_plugin_htmlrender import RasterOptions, RenderedImage
from entari_plugin_htmlrender.entari import HtmlRenderService

async def render_help(service: HtmlRenderService) -> RenderedImage:
    return await service.renderer.rasterize_markdown(
        "# Hello, Entari\n\nRendered by htmlrender.",
        raster=RasterOptions(width=720),
    )
```

返回的 `RenderedImage` 包含图片数据和元信息：

- `bytes(image)`：获取可直接发送给消息平台或写入文件的 `bytes`
- `image.width` / `image.height`：图片的实际像素尺寸
- `image.format` / `image.media_type`：图片格式（`"png"` / `"jpeg"`）与 MIME 类型

> [!WARNING]
>
> **不要把渲染对象存到全局变量**
>
> Entari 支持插件热重载与卸载。每次重载后旧的 `HtmlRenderService` 和 `HtmlRenderer` 都会被关闭。请在每次处理事件时通过依赖注入获取，不要缓存在模块级全局变量里。

## 需要浏览器能力时

Takumi 不执行 JavaScript，不支持网页导航或选择器截图，也不支持依赖 KaTeX 脚本的 Markdown 数学公式（交给 Takumi 会抛出 `UnsupportedDocumentFeatureError`）。

如果你的业务需要这些能力，请改用 [Playwright 与远程部署](<https://entanex.github.io/entari-plugin-htmlrender/pr-preview/pr-7/configuration/playwright/index.md>)。

## 下一步

- **选择最适合的方案**

  ---

  不确定选 Takumi、Playwright 还是 Python 绘图？看流程图一分钟决定。
- **渲染更多内容类型**

  ---

  学习渲染 HTML、Markdown、纯文本与 Jinja2 模板，以及分步准备与渲染。
- **使用模板与本地资源**

  ---

  配置路径白名单，在模板中安全引用本地样式、图片与远程资源。
- **用 Python 直接绘图**

  ---

  使用 Pillow 或 Skia 编写绘图函数，支持按模块组织与开发期热重载。
