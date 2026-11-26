# entari-plugin-htmlrender

面向 [Entari](https://github.com/ArcletProject/Entari) 的图片渲染插件，支持将 **HTML、Markdown、纯文本、Jinja2 模板** 渲染为图片，同时也内置了基于 **Pillow / Skia** 的 Python 绘图能力。

> [!TIP]
> **零浏览器开箱即用**：内置原生渲染引擎 **Takumi**，在进程内直接完成排版并输出 PNG / JPEG，无需安装和维护浏览器。遇到需要 JavaScript、网页截图或 Markdown 数学公式的场景，可随时切换到 **Playwright**（推荐使用远程浏览器服务）。

[在线文档](https://entanex.github.io/entari-plugin-htmlrender/) · [快速开始](docs/start/quickstart.md) · [示例代码](examples) · [从 0.1 升级到 0.2](docs/start/migration-v0.2.md)

---

## 核心特性

- **多种渲染输入**：统一接口支持 HTML、Markdown、纯文本与 Jinja2 模板。
- **可插拔渲染后端**：
  - **Takumi**：进程内原生排版，轻量快速，支持 SVG、布局测量、动画与字体管理。
  - **Playwright**：完整浏览器能力，支持本地启动或远程 WebSocket / CDP 连接，适用于动态脚本、网页截图与 KaTeX 数学公式。
- **独立的 Python 绘图**：不依赖 HTML 渲染后端，可直接用 **Pillow** 或 **Skia** 编写绘图函数（支持按文件或模块加载及热重载），或绘制轻量级 `RasterScene`。
- **默认安全的资源策略**：本地文件访问采用路径白名单，远程请求默认拦截内网地址并逐跳校验重定向。

## 快速开始

环境要求：Python `>=3.11,<4.0`，Entari `>=0.19.4,<0.20.0`。

### 1. 安装插件与渲染后端

基础包不包含任何渲染引擎，请按需选择附加依赖：

```bash
# 推荐：使用 Takumi 渲染静态内容（无需浏览器）
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"

# 需要浏览器能力（网页截图、JavaScript、数学公式）时安装
uv add "entari-plugin-htmlrender[playwright]>=0.2.0"

# 需要 Python 绘图时按需安装 pillow 或 skia
uv add "entari-plugin-htmlrender[pillow]>=0.2.0"
```

### 2. 在 Entari 中启用配置

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
```

### 3. 在插件中调用渲染

通过 Entari 依赖注入获取 `HtmlRenderer`，直接将内容渲染为 `RenderedImage`：

```python
from entari_plugin_htmlrender import HtmlRenderer, RasterOptions, RenderedImage


async def render_card(renderer: HtmlRenderer) -> RenderedImage:
    return await renderer.rasterize_markdown(
        "# Hello, Entari\n\nRendered with Takumi.",
        raster=RasterOptions(width=720),
    )
```

拿到 `RenderedImage` 后，调用 `bytes(image)` 即可获取图片字节流（支持 PNG 与 JPEG）。HTML、纯文本与模板分别对应 `rasterize_html()`、`rasterize_text()` 和 `rasterize_template()`。

> [!NOTE]
>
> - 渲染中文前，请先阅读 [Takumi 字体配置](docs/configuration/takumi.md#字体配置)。
> - 读取本地模板、图片或字体时，请将对应目录加入 [本地路径白名单](docs/configuration/resources-and-security.md#本地文件访问白名单)。

## 渲染方案对比

| 方案 | 适用场景 | 依赖与说明 |
| --- | --- | --- |
| [Takumi](docs/configuration/takumi.md) | 静态卡片、帮助菜单、模板图、SVG 与动画 | 安装 `[takumi]`；不支持 JavaScript 与 Markdown 数学公式 |
| [Playwright](docs/configuration/playwright.md) | 完整浏览器排版、JavaScript、网页截图、数学公式 | 安装 `[playwright]`；生产环境推荐连接远程浏览器服务 |
| [Pillow / Skia](docs/configuration/graphics.md) | 用 Python 代码直接绘像素图或图表 | 安装 `[pillow]` 或 `[skia]`；独立于 HTML 渲染后端 |

## 示例项目

- [Jinja2 模板渲染](examples/template_render)
- [Takumi SVG 与字体接口](examples/takumi_capability)
- [远程 Playwright 浏览器](examples/remote_browser)
- [Pillow / Skia Python 绘图](examples/graphics_render)
- [自定义 Provider 示例](examples/echo-provider)

## 开源协议

[MIT](LICENSE)
