# Pillow / Skia 绘图

[`example.py`](example.py) 演示独立的 `GraphicsRenderer` / `RasterScene` 路径。[`render_drawing.py`](render_drawing.py) 演示 `DrawingRenderer` 如何按名称执行 Python 绘图函数并返回 `RenderedImage`。两部分共用 Pillow/Skia native 后端，但入口和输入类型不同。

安装两种后端：

```bash
uv add "entari-plugin-htmlrender[pillow,skia]>=0.2.0"
```

从仓库根目录启动 Entari 时，可用下面的配置加载全部 Python 绘图示例：

```yaml
basic:
  external_dirs:
    - examples/graphics_render

plugins:
  htmlrender:
    provider: null
    graphics:
      backends: [pillow, skia]
      drawings:
        profile:
          backend: pillow
          path: examples/graphics_render/shared_cards/profile.py
          reload: true
        badge:
          backend: pillow
          module: shared_cards.badge
        skia-profile:
          backend: skia
          path: examples/graphics_render/skia_card.py
        pillow-card:
          backend: pillow
          path: examples/graphics_render/pillow_card.py
        card:
          backend: pillow
          path: examples/graphics_render/package_card/__init__.py
```

`path` 与 `module` 二选一。本目录的 `pillow_card.py`、`skia_card.py` 和 `shared_cards/profile.py` 都使用文件路径；`shared_cards/badge.py` 使用 `basic.external_dirs` 加入搜索路径后的模块名。`package_card` 只有 `__init__.py`，因此既可按文件路径加载，也可在搜索路径已配置时写 `module: package_card`。包入口的模块名不加 `.__init__`。

## 单文件与包入口

[`pillow_card.py`](pillow_card.py) 与 [`skia_card.py`](skia_card.py) 是各自后端的完整单文件回调。同步函数 `draw(canvas, data)` 必须返回 `None`：

- Pillow 的 `PillowCanvas` 提供 `.image`、`.draw`、`.width` 和 `.height`；
- Skia 的 `SkiaCanvas` 提供 `.canvas`、`.surface`、`.width` 和 `.height`。

[`package_card/__init__.py`](package_card/__init__.py) 演示整个包只有一个初始化文件。包初始化期间导入本地辅助模块与 Entari 子插件归属存在限制；需要共享 helper 时，参考下面的独立绘图模块结构。

## 共享 Python 包

[`shared_cards`](shared_cards) 包含两个绘图和一份共享样式：

```text
shared_cards/
|-- __init__.py
|-- colors.py
|-- profile.py
`-- badge.py
```

[`profile.py`](shared_cards/profile.py) 与 [`badge.py`](shared_cards/badge.py) 都通过 `from .colors import ...` 使用 [`colors.py`](shared_cards/colors.py)。在 Entari 中，两个入口加载同一个辅助模块实例。`profile` 开启 `reload: true`，因此修改 `colors.py` 后，下一次 `profile` 渲染会检查源码并触发依赖重载；`badge` 没有主动检查，但会使用由共享依赖重载后的当前函数和模块级值。

共享包必须保留 `__init__.py`，并使用真实的包与模块名称。多个绘图名称可以引用同一模块；不要通过不同导入路径把同一源码解析成两个模块名。已开启重载的绘图依赖本地 helper 时，该 helper 应由 Entari 管理；包外单文件的导入可标记为 `import shared_colors  # entari: plugin`，单独一行相同注释不能声明文件。已经属于其他插件的子插件不会被 HTMLRender 接管，主动重载可能报告归属冲突。

## 调用与输出

[`render_drawing.py`](render_drawing.py) 展示业务侧调用。事件处理函数可以直接注入 `DrawingRenderer`：

```python
from entari_plugin_htmlrender import RenderedImage
from entari_plugin_htmlrender.graphics import DrawingRenderer


async def profile_handler(drawings: DrawingRenderer) -> RenderedImage:
    return await drawings.render(
        "profile",
        {"name": "Ada", "title": "Profile"},
        width=640,
        height=360,
    )
```

`await drawings.render(name, data=None, *, width, height, background=..., output=...)` 返回 `RenderedImage`。发给消息或文件 API 时使用 `bytes(image)`；`.format`、`.media_type`、`.width` 和 `.height` 描述真实编码结果。默认输出 PNG；`RasterEncodeOptions(format="jpeg", quality=88, matte=RGBAColor(255, 255, 255))` 选择 JPEG 质量和不透明白底。`data` 必须是以字符串为键的映射，宽高是正整数物理像素。

也可以手动触发单个开发绘图的重载：

```python
await drawings.reload("profile")
```

自动重载只在 `reload: true` 的下一次对应渲染前检查；`reload()` 立即执行显式刷新，不受配置中的 `reload` 开关限制。导入失败时自动检查保留上一版并记录错误，手动调用把错误抛给调用方。重载按模块依次执行，不保证整个依赖图原子回滚。首次加载失败没有可回退版本。源码已成功导入但入口函数无效或执行异常时，本次渲染报错。需要持续后台监视时可另行启用 Entari 的 `::auto_reload`。修改 `graphics.drawings`、绘图名称或 backend 必须重载 HTMLRender 配置，不能只调用 `drawings.reload()`。

## 固定场景

[`example.py`](example.py) 使用 `GraphicsRenderer.rasterize(scene)` 绘制 backend-neutral 的纯色矩形。固定场景和 Python 绘图使用相同的 `graphics.max_pixels` 上限；`graphics.max_concurrency` 的额度在每个后端内共享，Pillow 与 Skia 分别计数；`graphics.max_commands` 只限制 `RasterScene.commands`。同一场景可以交给 `service.capabilities.pillow` 或 `service.capabilities.skia` 分别执行，但两个后端不保证相同像素或编码字节。完整场景说明见[绘制 RasterScene](../../docs/guides/raster-scenes.md)。

## 独立运行时

直接调用 `RuntimePlan.build_runtime()` 且未注入 Entari 绘图注册表时，每个绘图使用独立的私有模块命名空间。入口会在首次渲染时加载；`reload: true` 覆盖主文件和相对导入的包内 helper，但绝对导入仍使用普通 Python 模块缓存。该模式不提供多个绘图之间的共享模块生命周期，也不执行 Entari 的跨插件依赖传播。需要共享 helper、`# entari: plugin` 声明和完整依赖重载时，应在 Entari 宿主中运行。

## 进一步阅读

安装、回调签名、命名配置、输出选项、错误表和独立模式差异见仓库中的 [Python 绘图指南](../../docs/guides/python-drawing.md)。Pillow 与 Skia 的精确画布字段和平台限制见 [Pillow](../../docs/configuration/graphics/pillow.md) 与 [Skia](../../docs/configuration/graphics/skia.md)。HTML Provider 切换、RasterScene capability 与绘图名称的区别见[多引擎与切换](../../docs/guides/switching-engines.md)。

这些绘图文件是可信本地 Python 代码，没有沙箱。不要把消息或其他不可信输入用作源码路径、模块名或函数名；并发使用模块级状态时需要自行保证可安全访问。
