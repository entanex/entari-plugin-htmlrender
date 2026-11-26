# entari-plugin-htmlrender

面向 [Entari](https://github.com/ArcletProject/Entari) 的可插拔图片渲染插件：支持将 **HTML、Markdown、纯文本、Jinja2 模板** 渲染为图片，同时内置基于 **Pillow / Skia** 的独立 Python 绘图能力。

[在线文档](https://entanex.github.io/entari-plugin-htmlrender/) · [快速开始](docs/start/quickstart.md) · [配置参考](docs/configuration/overview.md) · [API 参考](docs/reference/api.md) · [示例项目](examples) · [升级到 0.2](docs/start/migration-v0.2.md)

> [!TIP]
> **无需浏览器即可出图**：推荐使用内置的 **Takumi** 原生渲染引擎，在进程内直接完成排版并输出 PNG / JPEG。需要完整浏览器 CSS、JavaScript、网页截图或 Markdown 数学公式时，可按需接入 **Playwright**（推荐连接独立的远程浏览器服务）。

---

## 功能概览

- **统一的内容出图接口**：通过 `HtmlRenderer` 一致地渲染 HTML、Markdown、纯文本与 Jinja2 模板，也支持用 `HtmlPreparer` 将“内容准备”与“后端出图”拆开复用。
- **可切换的 HTML 渲染后端**：
  - **Takumi**：基于 Rust 的进程内原生排版引擎，轻量快速，额外提供 SVG 输出、布局测量、动图编码与动态字体管理。
  - **Playwright**：支持远程 WebSocket / CDP 连接与本地启动，完整支持动态网页、选择器截图与 KaTeX 数学公式。
- **独立的 Python 绘图通道**：无需启用任何 HTML 引擎，即可直接用 **Pillow** 或 **Skia** 编写同步绘图函数（支持按文件/模块组织与开发期热重载），或渲染声明式 `RasterScene`。
- **默认安全的资源边界**：本地文件读取采用显式路径白名单（含符号链接校验），远程资源拉取默认拦截私网地址并逐跳校验重定向。

---

## 快速开始

运行环境要求：Python `>=3.11,<4.0`，Entari `>=0.19.4,<0.20.0`。

### 1. 安装插件与所需后端

基础包不包含任何渲染后端，请按实际场景选择可选依赖（可组合安装，如 `[takumi,pillow]`）：

```bash
# 推荐：使用 Takumi 渲染静态内容（无需安装浏览器）
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"

# 需要完整浏览器能力（JavaScript、网页截图、数学公式）
uv add "entari-plugin-htmlrender[playwright]>=0.2.0"

# 需要 Python 绘图能力（按需选择 pillow 或 skia）
uv add "entari-plugin-htmlrender[pillow]>=0.2.0"
```

### 2. 配置 Entari

在 Entari 配置文件中启用 `htmlrender`：

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
```

### 3. 在插件中调用

在事件处理函数中通过 Entari 依赖注入直接声明 `HtmlRenderer`（支持注入 `HtmlRenderer`、`HtmlPreparer`、`TemplateRenderer`、`ResourceAccess`、`GraphicsRenderer`、`DrawingRenderer` 或聚合入口 `HtmlRenderService`）：

```python
from entari_plugin_htmlrender import HtmlRenderer, RasterOptions, RenderedImage


async def render_card(renderer: HtmlRenderer) -> RenderedImage:
    return await renderer.rasterize_markdown(
        "# Hello, Entari\n\nRendered with Takumi.",
        raster=RasterOptions(width=720),
    )
```

返回的 `RenderedImage` 可直接通过 `bytes(image)` 提取 PNG / JPEG 字节流，并通过 `image.width`、`image.height`、`image.media_type` 读取元信息。HTML、纯文本与模板分别对应 `rasterize_html()`、`rasterize_text()` 和 `rasterize_template()`。

> [!NOTE]
>
> - **中文字体**：Takumi 默认字体主要覆盖拉丁字符，渲染中文前请参考 [Takumi 字体配置](docs/configuration/takumi.md) 注册字体文件。
> - **本地资源白名单**：读取本地模板、图片或字体前，请先将对应目录加入 `resources.local_access.allowed_paths`，详见 [资源访问、Filehost 与安全](docs/configuration/resources-and-security.md)。
> - **插件热重载**：请每次通过依赖注入获取渲染接口，不要将 `HtmlRenderService` 或 `HtmlRenderer` 缓存在模块级全局变量中。

---

## 渲染与绘图方案对比

| 方案 | 可选依赖 | 适用场景 | 主要边界 |
| --- | --- | --- | --- |
| [Takumi](docs/configuration/takumi.md) | `[takumi]` | 静态卡片、帮助菜单、Markdown、Jinja2 模板、SVG、测量与动图 | 不执行 JavaScript；不支持 Markdown 数学公式；样式需内联 |
| [Playwright](docs/configuration/playwright.md) | `[playwright]` | 复杂浏览器布局、JavaScript、网页/选择器截图、KaTeX 数学公式 | 需运行浏览器实例（生产环境推荐独立部署远程服务） |
| [Pillow / Skia](docs/configuration/graphics.md) | `[pillow]` / `[skia]` | 使用 Python 函数直接绘制卡片、拼图、矢量图形或 `RasterScene` | 独立于 HTML 引擎，不解析 HTML / Markdown |

其他可选依赖：`[filehost]`（远程浏览器本地大文件托管）、`[prometheus]`（Prometheus 指标）、`[sentry]`（Sentry 追踪）、`[all]`（安装全部可选组件）。

---

## 示例与文档

- **示例项目**
  - [Jinja2 模板渲染](examples/template_render)
  - [Takumi SVG 与字体接口](examples/takumi_capability)
  - [远程 Playwright 浏览器](examples/remote_browser)
  - [Pillow / Skia Python 绘图与热重载](examples/graphics_render)
  - [自定义 Provider 扩展](examples/echo-provider)
- **深入阅读**
  - [如何选择渲染方案](docs/start/choosing-backend.md) · [Python 绘图指南](docs/guides/python-drawing.md) · [生产最佳实践](docs/guides/best-practices.md) · [故障排查](docs/configuration/troubleshooting.md) · [参与贡献](CONTRIBUTING.md)

---

## 致谢

本项目基于开源社区的多项优秀工作构建与演进，在此一并致谢：

- **上游项目**
  - [kexue-z/nonebot-plugin-htmlrender](https://github.com/kexue-z/nonebot-plugin-htmlrender)：本项目最初移植并演进自 NoneBot 生态的 `nonebot-plugin-htmlrender`，感谢上游作者与贡献者奠定的设计与实践基础。
- **框架与运行时生态**
  - [ArcletProject/Entari](https://github.com/ArcletProject/Entari)、[ArcletProject/Launart](https://github.com/ArcletProject/Launart) 与 [ArcletProject/Letoderea](https://github.com/ArcletProject/Letoderea)：提供插件宿主、服务生命周期编排与依赖注入支持。
  - [agronholm/anyio](https://github.com/agronholm/anyio) 与 [aio-libs/aiohttp](https://github.com/aio-libs/aiohttp)：提供异步并发原语与内置 Filehost HTTP 服务。
- **渲染与图形引擎**
  - [kane50613/takumi](https://github.com/kane50613/takumi) 与 [BalconyJH/takumi-py](https://github.com/BalconyJH/takumi-py)：提供高性能的 Rust 进程内排版渲染能力与 Python 绑定。
  - [microsoft/playwright-python](https://github.com/microsoft/playwright-python)：提供本地与远程浏览器渲染及页面自动化支持。
  - [python-pillow/Pillow](https://github.com/python-pillow/Pillow) 与 [kyamagu/skia-python](https://github.com/kyamagu/skia-python)：提供 Python 2D 光栅与矢量绘图后端。
- **内容准备、样式与文档工具链**
  - [pallets/jinja](https://github.com/pallets/jinja)、[Python-Markdown/markdown](https://github.com/Python-Markdown/markdown)、[facelessuser/pymdown-extensions](https://github.com/facelessuser/pymdown-extensions) 与 [pygments/pygments](https://github.com/pygments/pygments)：提供模板引擎、Markdown 扩展解析与代码语法高亮。
  - [KaTeX/KaTeX](https://github.com/KaTeX/KaTeX) 与 [sindresorhus/github-markdown-css](https://github.com/sindresorhus/github-markdown-css)：提供内置数学公式排版与默认 Markdown 样式。
  - [zensical/zensical](https://github.com/zensical/zensical)、[mkdocstrings/mkdocstrings](https://github.com/mkdocstrings/mkdocstrings) 与 [squidfunk/mike](https://github.com/squidfunk/mike)：提供文档站点构建、API 参考自动生成与多版本文档管理。

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。
