# Pillow / Skia 绘图

[`example.py`](example.py) 演示原有的 `GraphicsRenderer` / `RasterScene`。Python 绘图则使用 `DrawingRenderer`：调用方传入名称、数据和尺寸，绘图函数直接使用 Pillow 或 Skia。

## 只有 `__init__.py` 的包

[`package_card/__init__.py`](package_card/__init__.py) 是一个完整的 Pillow 绘图入口。包里只需要这一个文件，直接定义 `draw(canvas, data)` 即可：

```text
package_card/
`-- __init__.py
```

从仓库根目录启动 Entari 时，可以按文件路径挂载：

```yaml
plugins:
  htmlrender:
    graphics:
      drawings:
        card:
          backend: pillow
          path: examples/graphics_render/package_card/__init__.py
          reload: true
```

如果已把 `examples/graphics_render` 加入 Python 搜索路径，也可以改用 `module: package_card`。模块名写包名即可，无需加 `.__init__`。调用 `await drawings.render("card", {"title": "Hello, Entari"}, width=320, height=180)` 就会执行包里的绘图函数。

修改 `__init__.py` 中的绘图代码也能热重载。需要本地辅助模块时，可在 `draw()` 内延迟导入；包初始化阶段立即导入本地辅助模块的限制见[绘图文档](../../docs/configuration/graphics/index.md)。

## 共享 Python 包

[`shared_cards`](shared_cards) 包含两个绘图和一份共享样式：

```text
shared_cards/
|-- __init__.py
|-- colors.py
|-- profile.py
`-- badge.py
```

[`profile.py`](shared_cards/profile.py) 与 [`badge.py`](shared_cards/badge.py) 都通过相对导入使用 [`colors.py`](shared_cards/colors.py)。在 Entari 中，两个绘图共享同一个辅助模块实例。

从仓库根目录启动 Entari 时，可以这样配置：

```yaml
basic:
  external_dirs:
    - examples/graphics_render

plugins:
  htmlrender:
    provider: null
    graphics:
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
```

安装对应依赖：

```bash
uv add "entari-plugin-htmlrender[pillow,skia]>=0.2.0,<0.3"
```

`path` 与 `module` 二选一。`basic.external_dirs` 在应用启动时加入 Python 搜索路径；更改这个目录后需要重启 Entari。也可以使用已安装包中的模块名。

[`render_drawing.py`](render_drawing.py) 展示业务侧的调用。事件处理函数可以直接注入 `DrawingRenderer`：

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

## 重载与引用

修改 `shared_cards/colors.py` 后，下一次调用 `profile` 会检查变化并通过 Entari 重载依赖。`badge` 虽然没有开启主动检查，也会使用更新后的共享模块。函数导入和模块级计算值由框架更新。

也可以手动触发：

```python
await drawings.reload("profile")
```

导入失败时保留原来的插件；手动重载会抛出错误。模块已成功加载但绘图入口无效，或 `draw()` 执行失败时，不回退到缓存的旧函数。需要后台监视，可以另行启用 Entari 的 `::auto_reload`。

包外的共享模块需要声明为插件时，在导入语句后添加标记，例如 `import shared_colors  # entari: plugin`。建议优先使用本示例这种带 `__init__.py` 的包。相互导入仍遵守 Python 初始化顺序，不能在对方尚未初始化时访问未定义的名字。

## 单文件与固定场景

[`pillow_card.py`](pillow_card.py) 和 [`skia_card.py`](skia_card.py) 是各自后端的单文件示例。绘图函数必须同步执行并返回 `None`；Pillow 画布提供 `.image` 和 `.draw`，Skia 画布提供 `.canvas` 和 `.surface`，两者都有 `.width` 和 `.height`。

`graphics.max_pixels` 与 `graphics.max_concurrency` 由固定场景和 Python 绘图共用；`graphics.max_commands` 只限制 `RasterScene`。

直接调用 `RuntimePlan.build_runtime()`、不经过 Entari 宿主时，每个绘图仍使用独立模块命名空间。其主动重载涵盖主文件与相对导入的辅助模块，不会更新绝对导入的普通 Python 缓存。

这些绘图文件是可信本地代码，没有沙箱。不要把用户输入当作源码路径或模块名；并发使用共享状态时，需要保证状态可安全访问。
