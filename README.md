# entari-plugin-htmlrender

Entari 的 provider-neutral HTML、Markdown、模板与栅格场景渲染库。

普通调用收口为五个显式 contract：`HtmlPreparer` 把内容准备为中立 `PreparedHtml`，`HtmlRenderer` rasterize 内容，`TemplateRenderer` render 模板 HTML，`ResourceAccess` fetch/publish 资源，`GraphicsRenderer` rasterize `RasterScene`。Entari 只负责组合并拥有 `HtmlRenderService` 的生命周期；业务代码不查找默认 runtime。

## 安装

项目支持 Python `>=3.11,<4.0` 与 Entari `>=0.19.4,<0.20.0`。按实际能力选择 extra：

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.2.0,<0.3"
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

在 Entari handler 中通过 concrete `HtmlRenderService` 类型参数取得 DI 注入的 service：

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

Entari handler 也可直接注入所需 contract；同一个签名可用于框架无关的业务函数：

```python
from entari_plugin_htmlrender import HtmlRenderer, RenderedImage


async def render_badge(renderer: HtmlRenderer) -> RenderedImage:
    return await renderer.rasterize_html("<b>ready</b>")
```

### Markdown 数学

Markdown 使用 `pymdownx.arithmatex` 的 `generic` 模式，并启用 `smart_dollar=True`。行内美元语法 `$x$` 要求美元紧贴内容，`\(x\)` 也是受支持的行内写法；`$ x $` 保留为原文。`$$...$$`、`\[...\]` 与独立的 `\begin{env}...\end{env}` 使用块级语义；`$$` 公式应独占段落，不要写成 `before $$x$$ after`。

Preparation 只给 Markdown treeprocessor 实际生成的公式容器添加内部 `data-htmlrender-arithmatex` 标记，公开样式仍是 `.arithmatex`。KaTeX 初始化脚本只处理带该标记的解析器结果，不会扫描没有标记的原始 HTML `.arithmatex` 容器。公式 preparation 会同时注入 KaTeX 脚本并设置 `DocumentRequirement.JAVASCRIPT`：Playwright 可以执行，Takumi rasterization 会以 `UnsupportedDocumentFeatureError` 拒绝该文档。

需要分别保留 preparation 与执行时，使用 `service.preparation` 和 `rasterize_prepared()`：

```python
from entari_plugin_htmlrender import RasterOptions
from entari_plugin_htmlrender.entari import HtmlRenderService


async def prepare_and_render(service: HtmlRenderService):
    prepared = await service.preparation.prepare_markdown("# Hello")
    return await service.renderer.rasterize_prepared(
        prepared,
        raster=RasterOptions(width=720),
    )
```

`HtmlRenderService` 直接暴露 `.preparation`、`.renderer`、`.templates`、`.resources`、`.graphics` 与 `.capabilities`。Playwright/Takumi 原生对象只通过 `service.capabilities` 的显式 lease 使用；`service.graphics` 使用配置的默认图形后端，也可同时启用 `graphics.backends: [pillow, skia]` 并通过 `service.capabilities.pillow` / `.skia` 调用。Takumi 的 `lease_api()` 提供编译、测量、SVG、节点、动画与字体等完整高级操作。

## 生命周期

插件通过 Entari `add_service` 注册 `HtmlRenderService`，并把它绑定到当前插件作用域。Launart 在 `preparing` 阶段启动所需 filehost 并按 `startup` 策略启动或探测 Provider；在 `cleanup` 阶段停止接纳新操作、排空在途操作、关闭 runtime，最后关闭 filehost。热卸载复用同一边界，业务代码不调用 service 的内部启动或关闭方法。

## 兼容性

`0.2.0` 是首条面向 Entari `0.19.x` 的发布线，最低 Python 为 3.11。从 `0.1.0` 升级时，应同时升级 Python 与 Entari；`0.1.0` 的安装命令和文档继续保留在对应历史版本中。发布面不包含 NoneBot 框架插件依赖，也不提供其他宿主框架的迁移 shim。插件保持 caller contracts 与 Entari DI 边界：handler 接收一次 plugin lifetime 内的 `HtmlRenderService`，框架无关业务函数继续依赖最小 contract，不读取进程级全局 runtime。

## 文档与示例

- [Entari 0.2 能力概览与升级](docs/start/migration-v0.2.md)
- [完整文档](https://entanex.github.io/entari-plugin-htmlrender/)
- [`examples/template_render`](examples/template_render)：Entari DI 与模板 rasterization
- [`examples/remote_browser`](examples/remote_browser)：远程 Playwright capability
- [`examples/takumi_capability`](examples/takumi_capability)：Takumi managed session
- [`examples/graphics_render`](examples/graphics_render)：`GraphicsRenderer` 与 `RasterScene`
- [`examples/echo-provider`](examples/echo-provider)：第三方 Provider v2 entry point

## License

项目使用 MIT License。启用第三方 Provider 或 native backend 前，请同时检查其依赖与分发许可。
