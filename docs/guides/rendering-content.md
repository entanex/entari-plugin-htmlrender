---
title: 渲染内容
description: 使用显式 runtime 渲染 HTML、Markdown、文本和 Jinja 模板
---

# 渲染内容

## HTML、Markdown 与文本

```python
from entari_plugin_htmlrender import (
    RuntimeSource,
    render_html,
    render_markdown,
    render_text,
)

async def render_all(runtime: RuntimeSource):
    html_image = await render_html("<main>Hello</main>", runtime=runtime)
    markdown_image = await render_markdown("# Hello", runtime=runtime)
    text_image = await render_text("Hello", runtime=runtime)
    return html_image, markdown_image, text_image
```

函数返回 `RenderedImage`。需要交给消息、HTTP 或文件 API 时调用 `bytes(image)`；`format`、`media_type`、`width` 与 `height` 描述真实编码结果。

Markdown 保留原始 HTML，不负责净化不可信内容。用户或模型输入应先按业务策略处理标签、属性和 URL；不需要富文本时使用 `render_text`。

## Jinja 模板

```python
from pathlib import Path

from entari_plugin_htmlrender import RuntimeSource, render_template

async def render_profile(runtime: RuntimeSource, username: str):
    return await render_template(
        Path("templates"),
        "profile.html",
        {"username": username},
        width=440,
        height=None,
        runtime=runtime,
    )
```

模板目录须列入 `resources.local_access.allowed_paths`；相对 stylesheet 与图片由Preparation 和 Resource Service 处理。

导航/selector 使用 [Playwright capability](browser-automation.md)，Takumi 的node/SVG/animation 使用 `.extensions.takumi`，无 HTML 的像素绘制使用[RasterScene](raster-scenes.md)。仓库示例只返回 artifact/bytes，不绑定消息 adapter。
