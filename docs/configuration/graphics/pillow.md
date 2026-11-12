---
title: Pillow 绘图后端
description: Pillow 固定场景与 Python 绘图的安装和使用说明
icon: lucide/image
---

# Pillow 绘图后端

Pillow 既能绘制 `RasterScene`，也能给 Python 绘图函数提供 `PIL.Image` 和 `PIL.ImageDraw`。它适合安装兼容性优先、使用普通 CPU 生成位图的环境。

## 安装

```bash
uv add "entari-plugin-htmlrender[pillow]>=0.2.0,<0.3"
```

`pillow` extra 安装 Pillow 12 或更高版本。缺少依赖却启用了 Pillow 时，渲染会抛出带安装提示的 `GraphicsBackendUnavailableError`，不会改用 Skia。Entari 会预加载配置的绘图源码；如果源码本身导入了缺失的 Pillow，错误会提前发生在插件加载阶段。

## 平台约束

Pillow 为受支持的 Python 和主流平台发布 wheel。官方 Linux wheel 已包含当前 `RasterScene` 与 PNG/JPEG 编码常用的图像库，正常安装不要求额外提供 EGL、OpenGL、Cairo 或 Fontconfig 动态库。若安装器回退到源码构建，请按 Pillow 的[构建说明](https://pillow.readthedocs.io/en/stable/installation/building-from-source.html)准备头文件和编译工具链。

## 启用

```yaml
plugins:
  htmlrender:
    provider: null
    graphics:
      drawings:
        profile:
          backend: pillow
          path: examples/graphics_render/shared_cards/profile.py
        badge:
          backend: pillow
          module: shared_cards.badge
```

绘图配置会自动启用 Pillow。固定场景也可以通过 `backends: [pillow]` 或兼容字段 `backend: pillow` 单独启用。同时使用 Pillow 与 Skia 时，把两者都写进 `backends`，再用 `backend` 指定 `service.graphics` 的默认后端。

## Python 绘图

绘图函数接收 `PillowCanvas`，必须是同步函数 `draw(canvas, data) -> None`：

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import ImageFont

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.pillow import PillowCanvas

def draw(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
    title = str(data.get("title", "Profile"))
    canvas.draw.rounded_rectangle(
        (40, 32, canvas.width - 40, canvas.height - 32),
        radius=24,
        fill=(30, 41, 59, 255),
        outline=(139, 92, 246, 255),
        width=2,
    )
    canvas.draw.text(
        (72, 82),
        title,
        font=ImageFont.load_default(size=32),
        fill=(249, 250, 251, 255),
    )
```

`canvas.image` 是已经创建的 RGBA 图像，`canvas.draw` 是它的绘图对象。可以直接使用 Pillow 的绘图接口，但不要把本次画布或临时状态保存为模块级全局值。完整示例见 [`shared_cards/`](../../../examples/graphics_render/shared_cards/)：`profile.py` 与 `badge.py` 都从 `colors.py` 导入同一个辅助函数和模块级 `palette`。调用方式见 [`render_drawing.py`](../../../examples/graphics_render/render_drawing.py)。

共享包让相对导入、模块身份和重载依赖都能由 Python 与 Entari 识别。若共享目录不在 Python 搜索路径 中，请先把其父目录放入 `basic.external_dirs`。路径映射、辅助模块声明和 `reload` 的完整规则见[绘图后端总览](index.md)。

## 运行规则

Pillow 不进入 `provider`。调用方可以使用 `service.graphics`、`service.capabilities.pillow`、`service.drawings`，也可以注入 `GraphicsRenderer` 或 `DrawingRenderer`。`graphics.max_pixels` 限制场景和绘图画布的像素数，`graphics.max_concurrency` 限制 Pillow 的并发任务数；`graphics.max_commands` 只用于 `RasterScene`。

输出沿用共享的 RGBA、source-over、JPEG 底色和质量规则。固定场景执行失败会转换为 `RasterBackendExecutionError`，Python 绘图或其编码失败会转换为 `DrawingBackendExecutionError`；绘图函数是异步函数、返回非 `None` 值或无法加载时，会产生对应的绘图错误。

固定场景的调用示例见[绘制 RasterScene](../../guides/raster-scenes.md)，配置、共享包与重载规则见[绘图后端总览](index.md)。
