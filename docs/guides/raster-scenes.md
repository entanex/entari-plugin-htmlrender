---
title: 绘制 RasterScene
description: 通过 GraphicsRenderer rasterize 物理像素场景
icon: lucide/shapes
---

# 绘制 RasterScene

本页用于纯色矩形等固定场景。需要文字、曲线、图片合成或直接调用 Pillow/Skia API 时，使用 [Python 绘图](python-drawing.md)。

```python
from entari_plugin_htmlrender.graphics import (
    FillRect,
    GraphicsRenderer,
    PixelRect,
    RasterScene,
    RGBAColor,
)

async def draw(graphics: GraphicsRenderer) -> bytes:
    scene = RasterScene(
        width=320,
        height=180,
        background=RGBAColor(15, 23, 42),
        commands=(
            FillRect(
                PixelRect(32, 32, 256, 116),
                RGBAColor(139, 92, 246),
            ),
        ),
    )
    return bytes(await graphics.rasterize(scene))
```

Entari handler 可以直接注入 `GraphicsRenderer`，或传入 `service.graphics`。Pillow 与 Skia 实现相同接口，默认后端由配置选择；同时启用两个后端时，也可逐次选择 `service.capabilities.pillow` 或 `.skia`，见[多引擎与切换](switching-engines.md)。

场景使用物理像素、半开矩形与概念上的 source-over 合成，但不保证两个 native
encoder 产生逐字节或逐像素相同输出。它们不是 HTML Provider，也不提供文本布局。
