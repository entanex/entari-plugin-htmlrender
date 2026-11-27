# 绘图后端配置（Pillow / Skia）

`graphics` 模块完全独立于 HTML 渲染后端：你可以只在机器人里启用绘图（`provider: null`），也可以与 Takumi 或 Playwright 同时启用。

## 配置示例

```yaml
plugins:
  htmlrender:
    graphics:
      backends: [pillow, skia] # (1)!
      max_pixels: 16777216     # (2)!
      max_concurrency: 2       # (3)!
      max_commands: 100000     # (4)!
      drawings:
        avatar_card:
          backend: pillow
          path: drawings/avatar_card.py
          function: draw
          reload: true
        badge:
          backend: skia
          module: my_drawings.badge
          function: render_badge
```

1. 可同时启用多个后端；列表第一项将作为 `service.graphics` 的默认后端。如果只用单个后端，也可以用兼容字段 `backend: pillow`（若与 `backends` 同时填写，`backend` 必须包含在 `backends` 中）。
2. `RasterScene` 与 Python 绘图共享的单张画布最大像素数（默认 1600 万像素）。
3. 每个后端独立计数的最大并发数（Pillow 最多 2 个的同时，Skia 也可运行 2 个）。同一后端下的 `RasterScene` 和 `DrawingRenderer` 共享该并发额度。
4. 仅限制 `RasterScene.commands` 的最大指令数，不影响 Python 绘图函数。

> [!NOTE]
>
> **自动启用绘图后端**
>
> 在 `graphics.drawings` 中引用的 `backend` 会自动启用对应绘图后端，即使没有显式把它写进 `graphics.backends`。但请确保已经安装了对应的 Python 可选依赖（`[pillow]` 或 `[skia]`），后端之间\*\*不会\*\*自动互相回退。

## `graphics.drawings.<name>` 字段说明

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `backend` | `"pillow" \\| "skia"` | 必填 | 该绘图函数使用的画布后端 |
| `path` | `Path \\| None` | `None` | `.py` 源码文件路径（相对进程当前目录，与 `module` 二选一） |
| `module` | `str \\| None` | `None` | Python 模块或包名（如 `my_drawings.card`，与 `path` 二选一） |
| `function` | `str` | `"draw"` | 模块级同步函数名（不可包含 `.`） |
| `reload` | `bool` | `false` | 是否在每次 `render()` 前按源码变化自动重载 |

## 平台与系统依赖对比

```bash
uv add "entari-plugin-htmlrender[pillow]>=0.2.0"
```

- 依赖 `pillow>=12.0.0`。
- 主流平台的预编译 wheel 已内置 PNG/JPEG 编解码库，\*\*不需要\*\*额外安装 EGL、OpenGL、Cairo 或 Fontconfig 等系统图形库。
- 适合追求跨平台省心部署的场景。

```bash
uv add "entari-plugin-htmlrender[skia]>=0.2.0"
```

- 依赖 `skia-python>=144.0.post2`。
- **仅提供预编译 wheel**（无源码包 sdist），**不支持 Alpine / musl** 与 32 位 Windows。
- **Linux**：要求 `manylinux_2_28`（glibc）以及以下系统共享库：
- `libegl1` (`libEGL.so.1`)
- `libgl1` (`libGL.so.1`)
- `libexpat1` (`libexpat.so.1`)
- `libstdc++6`、`zlib1g`
- **macOS**：macOS 11+；**Windows**：x64 / ARM64（Python 3.11–3.14）。

安装后建议用下面命令验证系统库是否齐全：

```bash
uv run python3 -c "import skia; print(skia.__name__)"
```

具体绘图函数写法、画布对象属性与模块化热重载指南，见 [Python 绘图指南](<https://entanex.github.io/entari-plugin-htmlrender/0.2.0/guides/python-drawing/index.md>)。
