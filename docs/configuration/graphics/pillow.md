---
title: Pillow 绘图后端
description: Pillow 固定场景与 Python 绘图的安装和使用说明
icon: lucide/image
---

# Pillow 绘图后端

Pillow 既能绘制 `RasterScene`，也能给 Python 绘图函数提供 `PIL.Image` 和 `PIL.ImageDraw`。它适合安装兼容性优先、使用普通 CPU 生成位图的环境。

## 安装

```bash
uv add "entari-plugin-htmlrender[pillow]>=0.2.0"
```

`pillow` extra 安装 Pillow 12 或更高版本。缺少依赖却启用了 Pillow 时，渲染会抛出带安装提示的 `GraphicsBackendUnavailableError`，不会改用 Skia。绘图源码导入 Pillow 时，缺失依赖也可能提前在 HTMLRender 加载阶段报错。

## 平台约束

Pillow 为受支持的 Python 和主流平台发布 wheel。官方 Linux wheel 已包含当前 `RasterScene` 与 PNG/JPEG 编码常用的图像库，正常安装不要求额外提供 EGL、OpenGL、Cairo 或 Fontconfig 动态库。若安装器回退到源码构建，请按 Pillow 的[构建说明](https://pillow.readthedocs.io/en/stable/installation/building-from-source.html)准备头文件和编译工具链。

## 启用

```yaml
basic:
  external_dirs:
    - examples/graphics_render

plugins:
  htmlrender:
    provider: null
    graphics:
      backends: [pillow]
      drawings:
        profile:
          backend: pillow
          path: examples/graphics_render/shared_cards/profile.py
```

绘图配置会自动启用 Pillow。固定场景也可以通过 `backends: [pillow]` 或兼容字段 `backend: pillow` 单独启用。同时使用 Pillow 与 Skia 时，把两者都写进 `backends`，再用 `backend` 指定 `service.graphics` 的默认后端。

## Python 绘图

绘图函数接收 `PillowCanvas`，必须同步执行并返回 `None`。回调可用的精确公开上下文如下：

| 属性 | 类型 | 语义 |
| --- | --- | --- |
| `canvas.image` | `PIL.Image.Image` | 本次新建的 RGBA 图像，初始填充调用方给出的背景 |
| `canvas.draw` | `PIL.ImageDraw.ImageDraw` | 与 `image` 对应的绘图对象 |
| `canvas.width` | `int` | 本次调用的物理像素宽度 |
| `canvas.height` | `int` | 本次调用的物理像素高度 |

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

上例的配置键是 `profile`，调用方使用 `await drawings.render("profile", data, width=640, height=360)` 执行它。函数必须声明至少两个位置参数，并能只用两个位置参数完成调用，第二个参数是本次 `Mapping[str, object]`。不能把回调写成 `async def`，也不要用返回值传递 `Image`；图片编码由 `DrawingRenderer` 完成。Pillow 的公开 adapter 模块只导出 `PillowCanvas` 与 `PillowRasterSceneRenderer`，业务代码应从 `entari_plugin_htmlrender.adapters.pillow` 导入画布类型。

`canvas.image` 可以直接使用 Pillow 图像 API，但应保持宽高不变。回调创建尺寸不同的替代图、替换 `canvas.image` 持有对象，或返回非 `None` 值都会失败。一次渲染的 canvas 和 draw 对象只在该回调期间有效，不要保存为模块级全局值，也不要跨渲染并发复用。完整示例见仓库的 `examples/graphics_render/shared_cards/`；`profile.py` 与 `badge.py` 都从 `colors.py` 导入同一个辅助函数和模块级 `palette`。

配置既可使用 `path`，也可使用 `module`，但不能同时提供两者。两文件示例分别展示文件路径和共享包模块名；完整配置、图片编码选项和重载说明见 [Python 绘图](../../guides/python-drawing.md)。共享目录不在 Python 搜索路径中时，先把其父目录放入 `basic.external_dirs`，更改后重启 Entari。

## 运行规则

Pillow 不进入 HTML 的 `provider`。调用方可以使用 `service.graphics`、`service.capabilities.pillow`、`service.drawings`，也可以注入 `GraphicsRenderer` 或 `DrawingRenderer`。`graphics.max_pixels` 限制场景和绘图画布的像素数，`graphics.max_concurrency` 限制 Pillow 的场景与回调合计并发数，Skia 单独计数；`graphics.max_commands` 只用于 `RasterScene`。

输出沿用共享的 RGBA、source-over、PNG/JPEG 编码、JPEG 质量与 matte 规则。`RenderedImage.data` 或 `bytes(image)` 提供编码字节。固定场景执行失败会转换为 `RasterBackendExecutionError`；Python 回调、尺寸检查或编码失败会转换为 `DrawingBackendExecutionError`。入口函数加载失败使用 `DrawingLoadError`，后端不可用使用 `GraphicsBackendUnavailableError`。

固定场景的调用示例见[绘制 RasterScene](../../guides/raster-scenes.md)，同时启用两种后端并逐次选择 capability 见[多引擎与切换](../../guides/switching-engines.md)。`PillowRasterSceneRenderer.rasterize(scene, *, output=RasterEncodeOptions())` 与 Python 绘图是不同公开入口，完整输入和错误表见 [Python 绘图](../../guides/python-drawing.md#common-errors)。

## 错误与限制

Pillow 回调运行在宿主工作线程中，但传进去的 `Image`、`ImageDraw` 和模块共享状态仍由应用负责保护。`graphics.max_concurrency` 限制 native 绘图任务的并发数，不保证两个不同绘图的模块级状态互斥。不要在回调中启动后台线程继续修改本次画布，因为回调返回后宿主可能立即开始编码。

需要文字排版、透明路径或抗锯齿能力时，直接调用 Pillow 支持的接口；不要把它们编码成 `RasterScene` 命令。需要与 Skia 比较相同场景时，可以提交同一个 `RasterScene`，但两个 native 后端不承诺逐像素或编码字节一致。重载语义、初始入口包和独立运行时的共享模块限制统一见[多引擎与切换](../../guides/switching-engines.md)和 [Python 绘图](../../guides/python-drawing.md)。
