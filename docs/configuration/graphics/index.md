---
title: 绘图后端
description: 使用 Pillow 或 Skia 绘制固定场景和 Python 卡片
---

# 绘图后端

绘图后端有两种用法：

| 需要的能力 | 使用入口 | 适合的内容 |
| --- | --- | --- |
| 固定的纯色矩形场景 | `service.graphics` / `GraphicsRenderer` | 可序列化、命令数量受限的场景 |
| 直接使用 Pillow 或 Skia 提供的接口 | `service.drawings` / `DrawingRenderer` | Python 代码生成的卡片、图表和装饰图 |

两种用法共用 `graphics.max_pixels` 和 `graphics.max_concurrency` 限制，以及 PNG/JPEG 编码规则。`graphics.max_commands` 只限制 `RasterScene.commands`，不能限制 Python 函数中的原生绘图调用。

## 配置

下面的两个 Pillow 绘图使用同一个 Python 包中的辅助模块。完整代码在 `examples/graphics_render/shared_cards/`。

```yaml
basic:
  external_dirs:
    - examples/graphics_render

plugins:
  htmlrender:
    provider: null
    graphics:
      backends: [pillow, skia]
      max_pixels: 16777216
      max_concurrency: 2
      max_commands: 100000
      drawings:
        profile:
          backend: pillow
          path: examples/graphics_render/shared_cards/profile.py
          reload: true
        badge:
          backend: pillow
          module: shared_cards.badge
          reload: false
        skia-profile:
          backend: skia
          path: examples/graphics_render/skia_card.py
```

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `graphics.backend` | `null` | 兼容的单选后端 |
| `graphics.backends` | `[]` | 显式启用的完整后端列表 |
| `graphics.drawings` | `{}` | 名称到 Python 绘图配置的映射 |
| `graphics.drawings.<name>.backend` | 必填 | `pillow` 或 `skia` |
| `graphics.drawings.<name>.path` | `null` | `.py` 文件路径 |
| `graphics.drawings.<name>.module` | `null` | 可导入的 Python 模块名 |
| `graphics.drawings.<name>.function` | `draw` | 模块中的绘图函数名 |
| `graphics.drawings.<name>.reload` | `false` | 下一次渲染前主动检查源码变化 |
| `graphics.max_pixels` | `16777216` | 单个场景或画布的像素上限 |
| `graphics.max_concurrency` | `2` | 每个后端的并发上限 |
| `graphics.max_commands` | `100000` | 单个 `RasterScene` 的命令上限 |

每项绘图必须设置 `backend`，并在 `path` 与 `module` 中恰好选择一个。配置引用的后端会自动启用，不必重复加入 `backends`，但仍需安装对应依赖：

```bash
uv add "entari-plugin-htmlrender[pillow,skia]>=0.2.0,<0.3"
```

### 文件路径与模块名

相对 `path` 以进程工作目录为基准。宿主把文件解析为正常的 Python 模块名；文件不在当前搜索路径内时，会挂载对应的包根目录，并在不再使用时释放。文件名和包名必须能组成合法的 Python 导入路径。

建议把共享代码组织成带 `__init__.py` 的包，通过 `basic.external_dirs` 配置导入目录，并统一使用相同的模块路径。示例中的 `profile` 与 `badge` 都属于 `shared_cards`。更改 Entari 的 `basic.external_dirs` 后需要重启应用。

模块名必须对应同一份源码。如果同名模块已经指向其他文件，或文件已作为普通模块导入而尚未由 Entari 管理，加载会报错。不要用不同导入路径把同一文件加载成两份独立模块。

### 只有 `__init__.py` 的包

包可以只包含一个 `__init__.py`，直接在里面定义绘图函数，无需再拆出 `card.py`：

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

将包的父目录加入 Python 搜索路径后，`module` 直接写包名：

```yaml
plugins:
  htmlrender:
    graphics:
      drawings:
        card:
          backend: pillow
          module: package_card
          reload: true
```

也可以把 `module: package_card` 替换为 `path: drawings/package_card/__init__.py`，路径按实际目录填写。两种方式都加载包本身，模块名不用写成 `package_card.__init__`。`__init__.py` 中可以直接定义函数、类和常量；修改其中的绘图代码同样支持热重载。Skia 也可以采用这种包结构，只需使用对应画布和后端配置。

## Python 绘图

Entari 事件处理函数可直接注入 `DrawingRenderer`，也可以使用 `service.drawings`：

```python
from entari_plugin_htmlrender import RenderedImage
from entari_plugin_htmlrender.graphics import DrawingRenderer, RGBAColor

async def render_profile(drawings: DrawingRenderer) -> RenderedImage:
    return await drawings.render(
        "profile",
        {"name": "Ada", "title": "Profile"},
        width=640,
        height=360,
        background=RGBAColor(15, 23, 42),
    )
```

`.names` 返回配置名称组成的 `frozenset[str]`。绘图文件提供同步函数 `draw(canvas, data) -> None`；返回其他值会报错。`data` 是本次调用的只读映射，其中的嵌套对象不会被深度复制或冻结。

- Pillow 的 `PillowCanvas` 提供 `.image`、`.draw`、`.width` 和 `.height`。
- Skia 的 `SkiaCanvas` 提供 `.canvas`、`.surface`、`.width` 和 `.height`。

每次渲染都会新建画布。函数可以直接调用对应后端的绘图 API，图片编码由宿主统一完成。PNG、JPEG 和 JPEG 底色通过 `RasterEncodeOptions` 选择，示例见 [Pillow](pillow.md) 和 [Skia](skia.md)。

## 相互引用与共享代码

Entari 加载 HTMLRender 时，会先收集绘图所在真实 Python 包中的模块名，并将它们声明为独立插件，再按实际导入关系加载源码。声明模块名不会执行尚未被导入的文件。多个绘图导入同一个辅助模块时，共享一个模块实例；每次绘制都从当前插件取得入口函数。

推荐把共享代码放在单独模块中：

```text
shared_cards/
|-- __init__.py
|-- colors.py
|-- profile.py
`-- badge.py
```

`profile.py` 与 `badge.py` 都可以写 `from .colors import card`。框架记录导入关系；`colors` 重载后，会更新引用它的函数绑定，必要时重新执行依赖方的模块级计算。

每次调用前都会检查包内是否增加了模块名，在实际导入前声明新模块；`reload: false` 也会做这一步，但不会主动重载源码。重载依赖以框架能够识别的导入关系为准；共享代码建议使用明确模块路径的 `import` 或 `from ... import 具体名字`，避免依赖星号导入或动态拼接的模块名。

`__init__.py` 可以直接包含绘图代码。热重载的限制针对包初始化期间立即导入本地辅助模块的情况：Entari 0.19.4 可能把这些模块归为子插件，其级联重载不能安全处理这里的全部依赖关系。开启主动重载时会检测并拒绝这种结构；需要辅助模块时，可以在 `draw()` 内延迟导入，或从独立的绘图模块中导入。

已经由其他插件加载的子插件不会被重新划归 HTMLRender。`reload: false` 可以借用它们，但主动或手动重载会报告归属限制；需要这类重载时，应从最初加载时就把相关模块声明为独立插件。

包外的独立辅助模块如果需要重载，应在导入处标记为 Entari 插件：

```python
import shared_colors  # entari: plugin
```

仅在文件顶层单独写一行 `# entari: plugin` 不会声明这个文件为插件。没有 `__init__.py` 的命名空间包也不会自动获得普通包的插件归属。开启主动重载时，如果发现本地辅助模块尚未由 Entari 管理，会提示改用真实包或声明插件导入。

绘图模块可以相互导入，但仍遵循 Python 的初始化规则：模块尚未初始化完成时，不能访问其中尚未定义的名字。把互相调用放进函数，或把共同依赖提取到第三个模块，通常更容易维护。框架不会自动解决任意循环导入。

## 源码加载与重载

### Entari 服务

绘图源码在 HTMLRender 插件加载阶段预加载。`reload: true` 会在下一次对应绘图调用前检查它及已登记依赖的源码变化，实际重载交给 Entari 的 `reload_plugin` / `reload_subplugin`。也可以手动执行：

```python
await drawings.reload("profile")
```

`reload: false` 只关闭主动检查，不会冻结共享依赖。其他绘图触发依赖重载，或者 Entari 的 `::auto_reload` 更新了模块后，该绘图也会使用当前函数。需要后台监视时，可以另行安装并启用 `::auto_reload`；两种触发方式使用同一份插件模块。

重载时源码导入失败，框架保留原来的插件。自动检查会记录错误，手动重载会把失败抛给调用方。首次加载没有可回退的版本，源码导入错误会导致插件加载失败。模块成功加载后，如果入口函数无效，或执行 `draw()` 时抛出异常，渲染会报错，不会使用缓存的旧函数。插件被禁用或卸载后也不能继续绘制。

框架的重载不是整张依赖图的事务回滚。模块之间存在顶层初始化、副作用或插件服务时，应按 Entari 自身的生命周期规则处理。修改 `graphics.drawings` 配置仍需经过插件配置重载。

HTMLRender 会等待已接纳的绘图完成后释放源码，只清理自己加载且不再被使用的插件。原本已由其他插件加载的模块不会被接管；仍有外部引用的源码及其必要导入路径会保留。

### 独立运行时

直接调用 `RuntimePlan.build_runtime()`、未注入 Entari 的源码注册表时，继续使用独立加载方式：每个绘图有专用模块命名空间，主动检查涵盖主文件及相对导入的辅助模块，绝对导入仍使用普通 Python 模块缓存。跨绘图共享模块和框架依赖传播需要通过 Entari 宿主运行。

## 固定场景

原有 `GraphicsRenderer` / `RasterScene` 继续可用。没有配置 `graphics.drawings` 时，后端选择规则如下：

| 配置 | 启用的后端 | `service.graphics` |
| --- | --- | --- |
| `backend`、`backends` 都省略 | 无 | 调用时提示补充配置 |
| 只设置 `backend` | 该项 | 该项 |
| 只设置 `backends` | 列表全部项 | 第一项 |
| `backend`、`backends` 都设置 | `backends` 全部项 | `backend` |

`backend` 与 `backends` 同时出现时，`backend` 必须包含在 `backends` 中。只配置 `drawings` 时，第一个绘图引用的后端会同时成为固定场景的默认后端。成功启用的后端还会提供 `runtime.capabilities.pillow` 或 `runtime.capabilities.skia`。

固定场景示例见[绘制 RasterScene](../../guides/raster-scenes.md)。HTML、Markdown、文本和模板渲染使用独立的[网页渲染后端](../providers/index.md)。

绘图文件按可信本地 Python 代码执行，没有沙箱。不要让消息或其他不可信输入决定 `path`、`module` 或 `function`；并发绘图需要自行保证共享状态可安全使用。
