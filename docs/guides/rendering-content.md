---
title: 渲染内容
description: 通过 HtmlRenderer rasterize HTML、Markdown、文本和 Jinja 模板
---

# 渲染内容

## HTML、Markdown 与文本

```python
from entari_plugin_htmlrender import HtmlRenderer, RasterOptions

async def render_all(renderer: HtmlRenderer):
    raster = RasterOptions(width=720)
    html_image = await renderer.rasterize_html(
        "<main>Hello</main>",
        raster=raster,
    )
    markdown_image = await renderer.rasterize_markdown(
        "# Hello",
        raster=raster,
    )
    text_image = await renderer.rasterize_text("Hello", raster=raster)
    return html_image, markdown_image, text_image
```

方法返回 `RenderedImage`。交给消息、HTTP 或文件 API 时调用 `bytes(image)`；`format`、`media_type`、`width` 与 `height` 描述真实编码结果。

Markdown 保留原始 HTML，不负责净化不可信内容。用户或模型输入应先按业务策略处理标签、属性和 URL；不需要富文本时使用 `rasterize_text()`。

## Markdown 数学与 JavaScript

Markdown 数学使用 `pymdownx.arithmatex(generic=True, smart_dollar=True)`。行内美元语法 `$x$` 要求美元紧贴内容，`\(x\)` 也是受支持的行内写法；`$ x $` 保持原文。块级 `$$...$$`、`\[...\]` 与独立的 `\begin{env}...\end{env}` 需要独占段落或进入块解析，`before $$x$$ after` 不提供块级展示语义。

Preparation 将公式统一输出为公开的 `.arithmatex` 容器，并仅给解析器实际生成的结果添加 `data-htmlrender-arithmatex`。Playwright 的 KaTeX 初始化脚本只处理 `.arithmatex[data-htmlrender-arithmatex]`，不执行页面全文 auto-render；没有内部标记的原始 HTML `.arithmatex` 容器会被忽略。

公式 preparation 会注入脚本并设置 `DocumentRequirement.JAVASCRIPT`。Playwright 可以执行并完成排版；Takumi 在执行阶段以 `UnsupportedDocumentFeatureError` 拒绝该文档，不会返回静态标记图像。需要 Takumi 输出视觉公式时，应提供已预渲染为静态 HTML/SVG 且不依赖 JavaScript 的内容。代码 span 与 fenced code 中的分隔符不会被当作公式。

## 分离 preparation 与执行

`HtmlPreparer` 可把内容先转换为中立 `PreparedHtml`。这样可以检查或复用 preparation 结果，再由当前配置的 Provider 执行：

```python
from entari_plugin_htmlrender import HtmlPreparer, HtmlRenderer, RasterOptions

async def prepare_then_render(
    preparation: HtmlPreparer,
    renderer: HtmlRenderer,
):
    prepared = await preparation.prepare_markdown("# Prepared once")
    return await renderer.rasterize_prepared(
        prepared,
        raster=RasterOptions(width=720),
    )
```

`PreparedHtml` 是 immutable value；`HtmlPreparer` 与 `HtmlRenderer` 则绑定当前 runtime lifetime。切换 Provider 后可以继续使用中立的 `rasterize_prepared()` 调用形态，但 execution 仍由新 runtime 完成。

## Jinja 模板

```python
from pathlib import Path

from entari_plugin_htmlrender import HtmlRenderer, RasterOptions, TemplateRef

async def render_profile(renderer: HtmlRenderer, username: str):
    return await renderer.rasterize_template(
        TemplateRef(Path("templates"), "profile.html"),
        {"username": username},
        raster=RasterOptions(width=440, height=None),
    )
```

模板目录须列入 `resources.local_access.allowed_paths`；相对 stylesheet 与图片由 preparation/resource pipeline 处理。

导航/selector 使用 [Playwright capability](browser-automation.md)，Takumi SVG/字体使用 `TakumiCapability`，无 HTML 的像素绘制使用 [RasterScene](raster-scenes.md)。仓库示例只返回 artifact/bytes，不绑定消息 adapter。
