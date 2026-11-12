---
title: Skia 绘图后端
description: Skia 固定场景与 Python 绘图的安装和使用说明
icon: lucide/pen-tool
---

# Skia 绘图后端

Skia 能绘制与 Pillow 相同的 `RasterScene`，也会给 Python 绘图函数提供 `skia.Canvas` 和 `skia.Surface`。选择和部署时要注意 `skia-python` 的平台限制。

## 安装

```bash
uv add "entari-plugin-htmlrender[skia]>=0.2.0,<0.3"
```

`skia` extra 安装 `skia-python>=144.0.post2`。缺少依赖却启用了 Skia 时，渲染会抛出带安装提示的 `GraphicsBackendUnavailableError`，不会改用 Pillow。Entari 会预加载配置的绘图源码；如果源码本身导入了缺失的 Skia，错误会提前发生在插件加载阶段。

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
plugins:
  htmlrender:
    provider: null
    graphics:
      drawings:
        skia-profile:
          backend: skia
          path: examples/graphics_render/skia_card.py
```

绘图配置会自动启用 Skia。固定场景也可以通过 `backends: [skia]` 或兼容字段 `backend: skia` 单独启用。同时使用 Pillow 与 Skia 时，把两者都写进 `backends`，再用 `backend` 指定 `service.graphics` 的默认后端。

## Python 绘图

绘图函数接收 `SkiaCanvas`，必须是同步函数 `draw(canvas, data) -> None`：

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import skia

if TYPE_CHECKING:
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.skia import SkiaCanvas

def draw(canvas: SkiaCanvas, data: Mapping[str, object]) -> None:
    paint = skia.Paint(AntiAlias=True)
    paint.setColor(skia.ColorSetARGB(255, 139, 92, 246))
    canvas.canvas.drawCircle(
        canvas.width / 2,
        canvas.height / 2,
        48,
        paint,
    )
```

`canvas.canvas` 是当前 `skia.Surface` 的绘图画布，`canvas.surface` 是这次渲染用的 surface。可以直接使用 `Paint`、`Rect`、`Path`、`Font` 等 Skia 接口，但不要把本次画布保存为模块级全局值。完整代码见 `examples/graphics_render/skia_card.py`，调用方式见 `examples/graphics_render/render_drawing.py`。

## 运行规则

Skia 不进入 `provider`。调用方可以使用 `service.graphics`、`service.capabilities.skia`、`service.drawings`，也可以注入 `GraphicsRenderer` 或 `DrawingRenderer`。`graphics.max_pixels` 限制场景和绘图画布的像素数，`graphics.max_concurrency` 限制 Skia 的并发任务数；`graphics.max_commands` 只用于 `RasterScene`。

固定场景不会自动改用其他后端：Skia 是默认后端但依赖不可用时，通过 `service.graphics` 调用会抛出 `GraphicsBackendUnavailableError`；Skia 只作为次级后端且不可用时，`service.capabilities.skia` 会抛出 `CapabilityUnavailableError`。固定场景执行失败会转换为 `RasterBackendExecutionError`，Python 绘图或其编码失败会转换为 `DrawingBackendExecutionError`；绘图函数是异步函数、返回非 `None` 值或无法加载时，会产生对应的绘图错误。

固定场景的调用示例见[绘制 RasterScene](../../guides/raster-scenes.md)，配置、共享包与重载规则见[绘图后端总览](index.md)。
