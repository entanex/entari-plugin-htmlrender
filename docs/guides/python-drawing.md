---
title: Python 绘图（Pillow / Skia）
description: 使用 Pillow 或 Skia 编写 Python 绘图函数，支持模块热重载与轻量级 RasterScene
icon: lucide/paintbrush
---

# Python 绘图（Pillow / Skia）

如果你习惯直接用 Python 代码画图（例如合成头像、绘制排行榜、拼图或数据图表），`entari-plugin-htmlrender` 内置了独立的 **Pillow** 与 **Skia** 绘图通道。

它完全独立于 HTML 渲染后端——你可以单独使用（`provider: null`），也可以与 Takumi / Playwright 并行启用。

插件提供两种绘图方式：

- **Python 绘图函数（`DrawingRenderer`）**：直接操作原生 Pillow 或 Skia 画布，最灵活，支持按文件或模块注册以及开发期热重载。
- **声明式矩形场景（`GraphicsRenderer` + `RasterScene`）**：与具体后端解耦的纯数据场景，适合只需要简单纯色矩形合成且希望跨后端复用的场景。

---

## 方式一：Python 绘图函数（推荐）

### 1. 安装依赖并配置绘图入口

先安装对应的可选依赖（`[pillow]` 或 `[skia]`），然后在 Entari 配置的 `graphics.drawings` 中注册你的绘图函数：

```yaml
plugins:
  htmlrender:
    graphics:
      drawings:
        profile_card: # (1)!
          backend: pillow
          path: drawings/profile_card.py # (2)!
          function: draw                 # (3)!
          reload: true                   # (4)!
```

1. 自定义绘图名称，后续调用 `drawings.render("profile_card", ...)` 时使用。
2. 指向 `.py` 文件（相对进程工作目录），或改用 `module: my_drawings.profile_card` 按模块导入（`path` 与 `module` 二选一）。
3. 模块级绘图函数名，默认为 `"draw"`。
4. 设为 `true` 后，每次调用 `render()` 前会自动检测源码变更并重新加载。

### 2. 编写绘图函数

绘图函数必须是一个**普通同步函数**（不能是 `async def`），接收 `(canvas, data)` 两个位置参数，直接修改画布并返回 `None`：

=== "Pillow 画布"

    `canvas` 为 `PillowCanvas`，提供 `.image`（RGBA 模式的 `PIL.Image.Image`）、`.draw`（`PIL.ImageDraw.ImageDraw`）、`.width` 和 `.height`：

    ```python
    from collections.abc import Mapping

    from entari_plugin_htmlrender.adapters.pillow import PillowCanvas

    def draw(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
        title = str(data.get("title", "Hello, Pillow"))
        # 绘制圆角背景卡片
        canvas.draw.rounded_rectangle(
            (24, 24, canvas.width - 24, canvas.height - 24),
            radius=20,
            fill=(30, 41, 59, 255),
        )
        canvas.draw.text((56, 60), title, fill=(248, 250, 252, 255))
    ```

=== "Skia 画布"

    `canvas` 为 `SkiaCanvas`，提供 `.canvas`（`skia.Canvas`）、`.surface`（`skia.Surface`）、`.width` 和 `.height`：

    ```python
    from collections.abc import Mapping
    import skia

    from entari_plugin_htmlrender.adapters.skia import SkiaCanvas

    def draw(canvas: SkiaCanvas, data: Mapping[str, object]) -> None:
        paint = skia.Paint(
            AntiAlias=True,
            Color=skia.Color(52, 81, 178, 255),
        )
        rect = skia.Rect.MakeXYWH(24, 24, canvas.width - 48, canvas.height - 48)
        canvas.canvas.drawRoundRect(rect, 20, 20, paint)
    ```

!!! warning "绘图函数编写约束"
    - 不要修改画布尺寸，也不要替换 `canvas.image` 对象本身。
    - 不要把 `canvas` 存到全局变量或传给后台线程——绘图结束后画布会被立即编码并回收。
    - 多个并发请求可能同时执行同一个绘图模块，请勿在模块全局变量里存放无锁可变状态。
    - 绘图函数直接运行在当前 Python 进程中，**没有沙箱隔离**，请只加载受信任的本地代码，切勿让用户输入决定 `path`、`module` 或 `function`。

### 3. 在插件中调用

注入 `DrawingRenderer`（或通过 `service.drawings` 访问），指定绘图名、数据与画布尺寸：

```python
from entari_plugin_htmlrender.graphics import (
    DrawingRenderer,
    RGBAColor,
    RasterEncodeOptions,
)

async def make_card(drawings: DrawingRenderer):
    return await drawings.render(
        "profile_card",
        {"title": "Entari 玩家名片"},
        width=800,
        height=360,
        background=RGBAColor(248, 250, 252, 255),
        output=RasterEncodeOptions(format="png"),
    )
```

### 模块化组织与热重载

如果你的绘图代码拆成了多个文件，或有多个绘图函数共用同一套工具模块，按以下方式组织即可让热重载正常工作：

1. **按包组织（推荐）**：把绘图目录放进 Entari 配置的 `basic.external_dirs`（修改后需重启 Entari），在包目录中放置 `__init__.py`，配置时写 `module: my_pkg`（不要写 `my_pkg.__init__`）。
2. **单文件引入本地辅助模块**：在单文件顶部标注 `# entari: plugin`，让 Entari 接管其依赖模块的热重载。
3. **触发时机**：
   - `reload: true` 采用**按需检测**（不是后台文件监听）：每次调用 `render(name)` 前会检查源码哈希，如有变化则触发 Entari 重载关联模块；若自动重载失败会记录日志并回退继续使用旧版本。
   - 也可以手动调用 `await drawings.reload("profile_card")` 强制重载（即使 `reload: false` 也生效；出错时直接抛异常）。
   - 如果修改了配置文件本身（新增绘图项、切换后端或改函数名），需要重载 `htmlrender` 插件。

---

## 方式二：声明式 `RasterScene`

如果你的图形非常简单（例如纯色色块拼接、占位图或测试图），且希望代码完全不依赖 `PIL` 或 `skia` 任何第三方库，可以使用 `GraphicsRenderer` + `RasterScene`：

```python
from entari_plugin_htmlrender.graphics import (
    FillRect,
    GraphicsRenderer,
    PixelRect,
    RGBAColor,
    RasterEncodeOptions,
    RasterScene,
)

async def draw_banner(graphics: GraphicsRenderer):
    scene = RasterScene(
        width=600,
        height=200,
        background=RGBAColor(24, 24, 27, 255),
        commands=(FillRect(PixelRect(24, 24, 552, 152), RGBAColor(52, 81, 178, 255)),),
    )
    return await graphics.rasterize(
        scene,
        output=RasterEncodeOptions(format="jpeg", quality=90),
    )
```

### 输出编码选项：`RasterEncodeOptions`

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `format` | `"png" \| "jpeg"` | `"png"` | 输出格式 |
| `quality` | `int \| None` | `None` | JPEG 质量（`0..100`，默认 `90`），仅 JPEG 可用 |
| `matte` | `RGBAColor \| None` | `None` | JPEG 透明底色（必须不透明 `alpha=255`，默认白色），仅 JPEG 可用 |

!!! note "跨后端说明"
    Pillow 与 Skia 均支持渲染 `RasterScene`，如果同时启用了两者，可以通过 `service.capabilities.pillow` 和 `service.capabilities.skia` 显式指定执行后端。注意两个后端的编码库不同，**不保证输出字节完全一致**，且后端之间**不会自动降级回退**。
