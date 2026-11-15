---
title: Python 绘图
description: 安装 Pillow 或 Skia，配置命名绘图并通过 DrawingRenderer 输出 PNG 或 JPEG
icon: lucide/brush
---

# Python 绘图

Python 绘图适合直接使用 Pillow 或 Skia 原生 API 生成卡片、图表和装饰图。为每个绘图配置名称和后端，业务代码通过同一个 `DrawingRenderer` 按名称调用，不需要判断实际后端。每次调用都会创建新画布，绘图函数只负责绘制，编码和输出由 HTMLRender 完成。

这种用法与固定 `RasterScene` 场景是两条独立入口：`DrawingRenderer.render()` 执行可信 Python 函数并返回一张 `RenderedImage`；`GraphicsRenderer.rasterize()` 消费可序列化的 `RasterScene`。两者使用相同的像素上限配置；同一后端的场景与回调共用并发额度，Pillow 与 Skia 分别计数。HTML Provider、`RasterScene` capability 与命名绘图分别选择，修改配置或逐次切换方式的差异见[多引擎与切换](switching-engines.md)。

## 1. 安装依赖

按需要安装；同时配置两种后端时选择“两种后端”：

=== "Pillow"

    ```bash
    uv add "entari-plugin-htmlrender[pillow]>=0.2.0"
    ```

=== "Skia"

    ```bash
    uv add "entari-plugin-htmlrender[skia]>=0.2.0"
    ```

=== "两种后端"

    ```bash
    uv add "entari-plugin-htmlrender[pillow,skia]>=0.2.0"
    ```

`pillow` extra 安装 Pillow 12 或更高版本，`skia` extra 安装 `skia-python>=144.0.post2`。Skia 有操作系统和 Linux 动态库要求，部署前查阅 [Skia 后端](../configuration/graphics/skia.md) 的平台约束。

## 2. 编写两个最小绘图

先准备一个可导入的目录，并通过 Entari 的 `basic.external_dirs` 把它加入 Python 搜索路径。下面两个文件都放在 `drawings/` 目录中。

=== "Pillow"

    Pillow 回调接收 `PillowCanvas`。其中 `canvas.image` 是本次新建的 RGBA `PIL.Image.Image`，`canvas.draw` 是对应的 `PIL.ImageDraw.ImageDraw`，`canvas.width` 和 `canvas.height` 是本次 `render()` 传入的物理像素尺寸：

    ```python title="drawings/pillow_badge.py"
    # drawings/pillow_badge.py
    from __future__ import annotations

    from typing import TYPE_CHECKING

    from PIL import ImageFont

    if TYPE_CHECKING:
        from collections.abc import Mapping

        from entari_plugin_htmlrender.adapters.pillow import PillowCanvas

    def draw(canvas: PillowCanvas, data: Mapping[str, object]) -> None:
        title = str(data.get("title", "Pillow"))
        canvas.draw.rounded_rectangle(
            (24, 24, canvas.width - 24, canvas.height - 24),
            radius=16,
            fill=(30, 41, 59, 255),
            outline=(139, 92, 246, 255),
            width=2,
        )
        canvas.draw.text(
            (48, 56),
            title,
            font=ImageFont.load_default(size=28),
            fill=(249, 250, 251, 255),
        )
    ```

=== "Skia"

    Skia 回调接收 `SkiaCanvas`。其中 `canvas.canvas` 是当前 `skia.Surface` 的 `skia.Canvas`，`canvas.surface` 是用于本次渲染的 surface，`canvas.width` 和 `canvas.height` 同样是物理像素尺寸：

    ```python title="drawings/skia_badge.py"
    # drawings/skia_badge.py
    from __future__ import annotations

    from typing import TYPE_CHECKING

    import skia

    if TYPE_CHECKING:
        from collections.abc import Mapping

        from entari_plugin_htmlrender.adapters.skia import SkiaCanvas

    def draw(canvas: SkiaCanvas, data: Mapping[str, object]) -> None:
        title = str(data.get("title", "Skia"))
        background = skia.Paint(AntiAlias=True)
        background.setColor(skia.ColorSetARGB(255, 30, 41, 59))
        canvas.canvas.drawRoundRect(
            skia.Rect.MakeXYWH(24, 24, canvas.width - 48, canvas.height - 48),
            16,
            16,
            background,
        )
        foreground = skia.Paint(AntiAlias=True)
        foreground.setColor(skia.ColorSetARGB(255, 249, 250, 251))
        typeface = skia.Typeface.MakeFromName(None)
        blob = skia.TextBlob.MakeFromString(title, skia.Font(typeface, 28))
        canvas.canvas.drawTextBlob(blob, 48, 72, foreground)
    ```

两个函数都必须同步执行，声明至少两个位置参数，并且能只用两个位置参数完成调用；可以有额外的可选参数，不能要求第三个必填参数或把入口全部写成仅限关键字参数。参数名不必是 `canvas` 和 `data`，返回值必须为 `None`。宿主已经用调用方给出的背景创建并填充画布；回调应保留宽高，不要创建一张不同尺寸的图片来替代本次画布。传递的 `data` 是本次调用的只读 `Mapping`，嵌套值不会被深度冻结。

## 3. 配置命名绘图

下面同时启用两种后端，并注册两个绘图名称：

```yaml
basic:
  external_dirs:
    - drawings

plugins:
  htmlrender:
    provider: null
    graphics:
      backends: [pillow, skia]
      drawings:
        pillow-badge:
          backend: pillow
          module: pillow_badge
          function: draw
          reload: true
        skia-badge:
          backend: skia
          module: skia_badge
          function: draw
          reload: true
```

`graphics.backends` 是后端列表，`graphics.drawings` 是从调用名称到源码定义的映射。每个绘图必须设置 `backend`，并在 `path` 与 `module` 中恰好提供一项；`function` 默认是 `draw`，`reload` 默认是 `false`。配置中的绘图后端会独立启用，即使没有把它写进 `backends` 也能工作，但对应的 native 依赖仍必须安装。

`module` 必须能由 Python 解析到 `.py` 源码，`path` 必须指向 `.py` 文件。相对路径按进程工作目录解析；`basic.external_dirs` 适合放置可导入包或单文件模块。绘图文件的模块名和函数名必须是合法 Python 名称。同一规范模块可以由多个绘图名称引用，各自选择同一个或不同的 `function`；不能把同一个文件通过不同导入路径解析成两个不同的模块名。

只有 `__init__.py` 的包也可以直接作为绘图入口。把函数写在包入口中，并把包父目录加入搜索路径：

```text
package_card/
`-- __init__.py
```

```python
# package_card/__init__.py
def draw(canvas, data):
    canvas.draw.text(
        (24, 24),
        str(data.get("title", "Hello, Entari")),
        fill=(255, 255, 255, 255),
    )
```

```yaml
plugins:
  htmlrender:
    graphics:
      drawings:
        card:
          backend: pillow
          module: package_card
```

这里写 `module: package_card`，不要写 `package_card.__init__`。也可以把 `module` 换成 `path: drawings/package_card/__init__.py`；两种写法都指向包本身。包初始化期间立即导入本地辅助模块可能干扰 Entari 的子插件归属；需要这类共享模块时，优先把绘图入口放到独立模块，或在 `draw()` 内延迟导入。

## 4. 用 DrawingRenderer 渲染

在 Entari 事件处理函数中直接注入 `DrawingRenderer`。名称必须与 `graphics.drawings` 的键完全一致：

```python
from entari_plugin_htmlrender import RenderedImage
from entari_plugin_htmlrender.graphics import (
    DrawingRenderer,
    RasterEncodeOptions,
    RGBAColor,
)

async def render_badge(drawings: DrawingRenderer) -> RenderedImage:
    return await drawings.render(
        "pillow-badge",
        {"title": "Hello, Pillow"},
        width=640,
        height=360,
        background=RGBAColor(15, 23, 42),
        output=RasterEncodeOptions(format="png"),
    )
```

公开签名是 `await drawings.render(name, data=None, *, width, height, background=RGBAColor(0, 0, 0, 0), output=RasterEncodeOptions(format="png", quality=None, matte=None))`。`width` 和 `height` 是正整数物理像素；`data` 必须是以字符串为键的映射；`background` 接收 `RGBAColor`；`output` 接收 `RasterEncodeOptions`。`drawings.names` 返回所有已配置名称组成的 `frozenset[str]`，可以在调用前检查名称。

`RGBAColor(red, green, blue, alpha=255)` 的四个通道都必须是 0 到 255 的整数。调用 `service.drawings` 与注入 `DrawingRenderer` 指向同一个运行时入口，例如在事件处理函数中接收 `HtmlRenderService` 后调用 `service.drawings.render(...)`。`graphics.max_pixels` 限制画布总像素数，`graphics.max_concurrency` 对每个后端分别限制并发：同一后端的 `RasterScene` 与 Python 绘图共用额度，Pillow 与 Skia 各自计数；`graphics.max_commands` 只限制 `RasterScene` 命令，对回调内部的 Pillow/Skia 调用没有计数作用。

## 5. 取得 PNG 或 JPEG 字节

`render()` 返回 `RenderedImage`。要发送字节时使用 `bytes(image)`，其 `.data` 保存同一份 `bytes`，`.format` 为 `"png"` 或 `"jpeg"`，`.media_type` 为 `image/png` 或 `image/jpeg`，宽高来自实际编码结果：

```python
image = await drawings.render(
    "skia-badge",
    {"title": "Hello, Skia"},
    width=640,
    height=360,
    output=RasterEncodeOptions(
        format="jpeg",
        quality=88,
        matte=RGBAColor(255, 255, 255),
    ),
)
payload: bytes = bytes(image)
assert image.media_type == "image/jpeg"
```

PNG 是默认格式。`quality` 和 `matte` 只能与 `format: "jpeg"` 一起使用；质量范围是 0 到 100，未提供时使用 90；JPEG matte 必须是 alpha 为 255 的 `RGBAColor`，未提供时使用不透明白色。JPEG 会先把完整 RGBA 画布合成到 matte 上。两个后端遵守相同语义，但由于 native 抗锯齿、颜色量化和编码器不同，不应要求跨后端的编码字节完全一致。

## 6. 共享模块与源码重载

推荐把共享代码放在带 `__init__.py` 的包里，让绘图入口和辅助模块保持真实模块名。仓库的 `examples/graphics_render/shared_cards/` 示例中有两个绘图，都通过相对导入使用同一份 `colors.py`：

```text
shared_cards/
|-- __init__.py
|-- colors.py
|-- profile.py
`-- badge.py
```

```python
# shared_cards/profile.py
from .colors import card, marker, palette, text

def draw(canvas, data):
    inner = card(canvas)
    marker(canvas)
    text(
        canvas,
        str(data.get("name", "Ada")),
        (inner[0], inner[1]),
        size=24,
        color=palette["foreground"],
    )
```

Entari 在 HTMLRender 加载时声明包内可导入模块，再按实际导入关系加载源码。多个绘图导入同一个辅助模块时使用同一模块实例；辅助模块重载后，依赖它的函数绑定和需要重新计算的模块级值会更新。使用明确的相对或绝对导入；星号导入和动态拼装的模块名不利于建立重载依赖。

> [!NOTE]
> `reload: true` 在对应绘图的下一次调用前检查源码，不会启动后台文件监视。修改配置本身仍需重新加载 HTMLRender 插件。

`reload: true` 会在下一次对应渲染前检查源码摘要，并将变化交给 `reload_plugin` 或 `reload_subplugin`。检查涵盖该绘图可达的已登记模块，包括共享导入依赖；检查是“下一次渲染时”发生，不是持续后台监视。`reload: false` 不主动检查源码，但其他绘图触发的依赖重载或 Entari 外部重载仍可能更新它的入口。需要持续监视时可以另行启用 Entari 的 `::auto_reload`。

也可以显式重载。它会立即检查并重载入口，即使源码未变或配置为 `reload: false` 也会执行：

```python
await drawings.reload("pillow-badge")
```

自动重载遇到语法或导入失败时会记录错误，并继续使用失败模块的上一版；显式 `reload()` 会把错误抛给调用方。重载按依赖顺序逐个执行，已经成功替换的模块不会因后续失败而回滚，因此不保证整个依赖图的原子替换。首次加载没有旧版本可回退，源码导入失败会使 HTMLRender 加载失败。源码已经成功重新导入，但入口函数无效或执行时抛错，则本次渲染报错。修改 `graphics.drawings`、`backend` 或 `function` 等配置需要重新加载 HTMLRender 配置，不能靠 `drawings.reload()` 完成。

包周围还有几项需要遵守的实际限制。开启重载的绘图依赖若是本地模块却未被 Entari 管理，加载会拒绝它；包外单文件可写成 `import shared_colors  # entari: plugin` 来声明依赖导入，单独一行注释不能声明文件。已经属于其他插件的子插件不会被 HTMLRender 接管，主动重载可能报告归属冲突。相互导入仍遵循 Python 初始化顺序，HTMLRender 不会自动解决任意循环导入。包初始化阶段直接导入本地辅助模块的限制与替代写法见上一节的说明。

修改 `basic.external_dirs` 后要重启 Entari。不要把一次 `render()` 得到的画布、回调或 `DrawingRenderer` 保存为模块级单例；它们属于当前插件运行时。插件关闭或卸载时，HTMLRender 等待已接纳的绘图结束，再释放自己拥有的源码。单独重载绘图源码不保证先等待所有正在执行的回调结束。绘图源码是可信本地代码，没有沙箱；不要让不可信输入选择 `path`、`module` 或 `function`，并发回调共享状态时也要自行同步。

`RuntimePlan.build_runtime()` 未注入 Entari 源码注册表时会使用独立加载器。它按配置为每个绘图建立私有模块命名空间，首次实际渲染时加载入口，并让 `reload: true` 在下一次渲染前检查入口及相对的包内导入；其主动重载不依赖 Entari 插件注册表。绝对导入仍使用普通 Python 模块缓存，多个绘图不会自动共享同一份辅助模块，也不会获得 Entari 的跨插件依赖传播。需要这些能力时，应在 Entari 宿主中运行；独立模式仍可显式调用 `drawings.reload(name)`。

## 7. 处理常见错误 {: #common-errors }

| 现象 | 原因与处理 |
| --- | --- |
| 加载时提示模块无法解析 | 检查 `module` 的包路径，或把父目录放入 `basic.external_dirs` 后重启；`path` 必须是现有 `.py` 文件 |
| `DrawingNotFoundError` | `render()` 的名称不是 `graphics.drawings` 的键；用 `drawings.names` 对照检查 |
| `GraphicsBackendUnavailableError` | 配置选择了未安装或无法加载的 native 后端；安装对应 extra，Skia 还要检查宿主动态库 |
| `DrawingLoadError` | 源码无法加载、函数不是同步可调用对象、参数无法绑定，或模块归属与重载依赖不满足要求；按错误中的源码路径修正 |
| `DrawingBackendExecutionError` | 回调执行或图片编码失败；检查回调异常、Pillow/Skia API 参数与尺寸是否保持不变 |
| `InvalidRenderInputError` | 名称、数据映射、宽高、背景、编码选项或像素预算无效；错误对象的 `field` 会指出字段 |
| 修改后仍显示旧图片 | 确认该绘图 `reload: true` 或手动调用 `reload()`；仅修改配置时重新加载 HTMLRender 配置 |

`DrawingRenderer` 返回的是 `RenderedImage`，不会把 Pillow `Image` 或 `skia.Surface` 暴露为结果。需要固定、可序列化的纯色矩形场景时使用单独的 `GraphicsRenderer` / `RasterScene` 路径，参见[绘制 RasterScene](raster-scenes.md)。多后端配置与逐次选择见[多引擎与切换](switching-engines.md)；各后端的安装、平台约束和更完整的示例见 [Pillow](../configuration/graphics/pillow.md)、[Skia](../configuration/graphics/skia.md) 与仓库的 `examples/graphics_render/README.md`。
