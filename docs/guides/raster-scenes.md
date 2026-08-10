---
title: 绘制 RasterScene
description: 通过 Pillow 或 Skia capability 渲染物理像素场景
---

# 绘制 RasterScene

```python
from entari_plugin_htmlrender import RuntimeSource, resolve_runtime
from entari_plugin_htmlrender.graphics import (
    FillRect,
    PixelRect,
    RasterScene,
    RenderRasterSceneRequest,
    RGBAColor,
)

async def draw(runtime: RuntimeSource) -> bytes:
    renderer = resolve_runtime(runtime).extensions.pillow
    scene = RasterScene(
        width=320,
        height=180,
        background=RGBAColor(15, 23, 42),
        commands=(FillRect(PixelRect(32, 32, 256, 116), RGBAColor(139, 92, 246)),),
    )
    image = await renderer.render(RenderRasterSceneRequest(scene))
    return bytes(image)
```

Pillow 与 Skia 实现同一个 `RasterSceneRenderer` protocol。场景使用物理像素、半开矩形与概念上的 source-over 合成，但不保证两个 native encoder 产生逐字节或逐像素相同输出。它们不是 HTML Provider，也不提供文本布局。
