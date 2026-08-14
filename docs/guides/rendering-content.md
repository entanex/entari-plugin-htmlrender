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

模板目录须列入 `resources.local_access.allowed_paths`；相对 stylesheet 与图片由preparation/resource pipeline 处理。

导航/selector 使用 [Playwright capability](browser-automation.md)，Takumi SVG/字体使用 `TakumiCapability`，无 HTML 的像素绘制使用 [RasterScene](raster-scenes.md)。仓库示例只返回 artifact/bytes，不绑定消息 adapter。
