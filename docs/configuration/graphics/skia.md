---
title: Skia 绘图后端
description: Skia 固定场景与 Python 绘图的安装和使用说明
icon: lucide/pen-tool
---

# Skia 绘图后端

Skia 能绘制与 Pillow 相同的 `RasterScene`，也会给 Python 绘图函数提供 `skia.Canvas` 和 `skia.Surface`。选择和部署时要注意 `skia-python` 的平台限制。

## 安装

```bash
uv add "entari-plugin-htmlrender[skia]>=0.2.0"
```

`skia` extra 安装 `skia-python>=144.0.post2`。缺少依赖却启用了 Skia 时，渲染会抛出带安装提示的 `GraphicsBackendUnavailableError`，不会改用 Pillow。绘图源码导入 `skia` 时，缺失依赖也可能提前在 HTMLRender 加载阶段报错。

## 平台约束

!!! warning "Skia 发布平台限制"

    `skia-python` 当前只发布预编译 wheel，没有 sdist 或 musllinux wheel。Linux wheel 要求 manylinux 2.28 兼容环境；macOS 需要 11 或更高版本。Windows x64 与 ARM64 分别覆盖 Python 3.11–3.14，且没有 win32 wheel。Alpine/musl 或较旧 glibc 镜像不应启用 `skia` extra；`all` extra 也包含 Skia，具有相同平台约束。

### Linux 动态库

`skia-python==144.0.post2` 的 x86-64 与 AArch64 Linux wheels 都捆绑了 Fontconfig、FreeType 与 libpng，但原生模块仍直接链接以下宿主库：

- `libEGL.so.1`；
- `libGL.so.1`；
- `libexpat.so.1`；
- glibc、libstdc++、libgcc 与 zlib 基线运行库。

Python extra、PyOpenGL 或其他 Python 包装库都不会提供这些 ELF shared objects。Debian/Ubuntu 的最小镜像应在安装 Python 包前补齐运行库：

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libegl1 \
        libexpat1 \
        libgl1 \
        libstdc++6 \
        zlib1g
```

构建镜像后执行导入检查，避免到测试收集或应用启动时才发现动态库缺失：

```bash
uv run python3 -c "import skia"
```

`ImportError: libEGL.so.1: cannot open shared object file` 表示缺少 `libegl1`，不是 `skia` extra 未解析成功。修复 `libEGL` 后如果报告 `libGL.so.1` 或 `libexpat.so.1`，分别检查 `libgl1` 与 `libexpat1`。字体文件仍需按实际字符集随部署提供。

## 启用

```yaml
basic:
  external_dirs:
    - examples/graphics_render

plugins:
  htmlrender:
    provider: null
    graphics:
      backends: [skia]
      drawings:
        skia-profile:
          backend: skia
          path: examples/graphics_render/skia_card.py
```

绘图配置会自动启用 Skia。固定场景也可以通过 `backends: [skia]` 或兼容字段 `backend: skia` 单独启用。同时使用 Pillow 与 Skia 时，把两者都写进 `backends`，再用 `backend` 指定 `service.graphics` 的默认后端。

## Python 绘图

绘图函数接收 `SkiaCanvas`，必须同步执行并返回 `None`。回调可用的精确公开上下文如下：

| 属性 | 类型 | 语义 |
| --- | --- | --- |
| `canvas.canvas` | `skia.Canvas` | 当前 raster surface 的绘图画布，已填充调用方给出的背景 |
| `canvas.surface` | `skia.Surface` | 用于本次编码的 raster surface |
| `canvas.width` | `int` | 本次调用的物理像素宽度 |
| `canvas.height` | `int` | 本次调用的物理像素高度 |

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import skia

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.skia import SkiaCanvas

def draw(canvas: SkiaCanvas, data: Mapping[str, object]) -> None:
    title = str(data.get("title", "Skia"))
    paint = skia.Paint(AntiAlias=True)
    paint.setColor(skia.ColorSetARGB(255, 139, 92, 246))
    canvas.canvas.drawCircle(
        canvas.width / 2,
        canvas.height / 2,
        48,
        paint,
    )
    text_paint = skia.Paint(AntiAlias=True)
    text_paint.setColor(skia.ColorSetARGB(255, 249, 250, 251))
    typeface = skia.Typeface.MakeFromName(None)
    blob = skia.TextBlob.MakeFromString(title, skia.Font(typeface, 28))
    canvas.canvas.drawTextBlob(blob, 40, 64, text_paint)
```

上例的配置键是 `skia-profile`，调用方使用 `await drawings.render("skia-profile", data, width=640, height=360)` 执行它。函数必须声明至少两个位置参数，并能只用两个位置参数完成调用，第二个参数是本次 `Mapping[str, object]`。不能把回调写成 `async def`，也不要用返回值传递 surface 或 image；图片编码由 `DrawingRenderer` 完成。业务代码应从 `entari_plugin_htmlrender.adapters.skia` 导入 `SkiaCanvas`，不要依赖 renderer 内部的 facade。

`canvas.canvas` 可以调用 Skia 公开的 `Paint`、`Rect`、`Path`、`Font` 等 native API，且应保留 surface 的宽高。一次渲染的 canvas 与 surface 只在该回调期间有效，不要保存为模块级全局值，也不要在回调返回后继续由后台线程修改。完整示例见仓库的 `examples/graphics_render/skia_card.py`；该文件还演示圆角矩形、描边和文本绘制。

配置既可使用 `path`，也可使用 `module`，但不能同时提供两者。路径、模块加载、多个绘图名称和源码重载的完整步骤见 [Python 绘图](../../guides/python-drawing.md)；同时启用 Pillow 与 Skia 并按名称选择的方式见[多引擎与切换](../../guides/switching-engines.md)。

## 运行规则

Skia 不进入 HTML 的 `provider`。调用方可以使用 `service.graphics`、`service.capabilities.skia`、`service.drawings`，也可以注入 `GraphicsRenderer` 或 `DrawingRenderer`。`graphics.max_pixels` 限制场景和绘图画布的像素数，`graphics.max_concurrency` 限制 Skia 的场景与回调合计并发数，Pillow 单独计数；`graphics.max_commands` 只用于 `RasterScene`。

固定场景不会自动改用其他后端：Skia 是默认后端但依赖不可用时，通过 `service.graphics` 调用会抛出 `GraphicsBackendUnavailableError`；Skia 只作为次级后端且不可用时，`service.capabilities.skia` 会抛出 `CapabilityUnavailableError`。Python 绘图绑定自己的 `backend`，也不会回退到 Pillow。固定场景执行失败会转换为 `RasterBackendExecutionError`，Python 回调、尺寸检查或编码失败会转换为 `DrawingBackendExecutionError`。入口函数加载失败使用 `DrawingLoadError`。

输出沿用共享的 RGBA、source-over、PNG/JPEG 编码、JPEG 质量与 matte 规则。`RenderedImage.data` 或 `bytes(image)` 提供编码字节。Pillow 与 Skia 可能使用不同的 premultiplication、抗锯齿和编码器，因此不要要求两个后端对同一输入生成相同像素或相同字节。两个 native 后端共用的场景入口与逐次 capability 选择见[多引擎与切换](../../guides/switching-engines.md)。

## 错误与限制

加载 `skia` 失败时先运行前文的 `uv run python3 -c "import skia"`，优先排查 wheel 平台或动态库，而不是调整 `provider`。Skia 的文本整形、字体 fallback 和中日韩字形覆盖取决于 `skia-python` 与宿主字体；`Typeface.MakeFromName(None)` 得到默认字体，不代表任意语言都有完整字形。需要固定字体时，应显式选择 typeface，并在目标镜像中安装或打包相应字体。

`graphics.max_concurrency` 限制宿主接纳的 native 绘图任务数，不自动同步绘图模块中的共享状态。回调运行在工作线程中，不要启动后台线程继续使用本次 surface。插件关闭或卸载时，宿主等待已接纳的绘图结束，自动或显式重载的失败回退规则见 [Python 绘图](../../guides/python-drawing.md#common-errors)。固定场景的调用和像素语义见[绘制 RasterScene](../../guides/raster-scenes.md)。
