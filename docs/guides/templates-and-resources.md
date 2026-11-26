---
title: Jinja2 模板与资源加载
description: 渲染 Jinja2 模板、配置本地路径白名单、读取远程资源与控制资源加载策略
icon: lucide/folder-open
---

# Jinja2 模板与资源加载

在实际插件开发中，卡片、战绩图和榜单通常使用 **Jinja2 模板** 编写，并伴随本地图片、CSS 样式或远程头像。本页介绍如何安全地渲染模板与加载各类资源。

## 渲染 Jinja2 模板

使用 `TemplateRef(root, name)` 指定模板根目录和相对文件名，再传给 `renderer.rasterize_template()`：

```python
from pathlib import Path

from entari_plugin_htmlrender import HtmlRenderer, RasterOptions, TemplateRef


async def render_profile(renderer: HtmlRenderer, username: str):
    return await renderer.rasterize_template(
        TemplateRef(Path("templates"), "profile.html"), # (1)!
        {"username": username, "level": 42},
        raster=RasterOptions(width=440),
    )
```

1. `TemplateRef.name` 必须是相对 POSIX 路径（如 `"cards/profile.html"`），不允许包含 `..` 或反斜杠 `\`。

![模板渲染示例](../template2pic.png)

### 只生成 HTML 字符串（不出图）

如果只想把 Jinja2 模板渲染成 HTML 字符串（例如调试或交给其他系统），注入 `TemplateRenderer` 即可，甚至不需要配置任何 HTML 渲染后端：

```python
from pathlib import Path

from entari_plugin_htmlrender import TemplateRef, TemplateRenderer


async def build_html(templates: TemplateRenderer) -> str:
    rendered = await templates.render(
        TemplateRef(Path("templates"), "profile.html"),
        {"username": "Entari"},
    )
    return str(rendered)
```

!!! tip "自定义过滤器与扩展"
    `rasterize_template()` 和 `templates.render()` 都支持传入 `filters={...}` 和 `extensions=(...)`。为了命中 Jinja2 环境缓存，请尽量复用具名函数作为 filter，避免每次调用临时创建 `lambda`。

## 本地文件访问白名单

出于安全考虑，插件**默认禁止读取任何本地文件**。`TemplateRef.root`、当前工作目录或 HTML 中的 `<base>` 都不会自动获得读取权限。

使用本地模板、图片或字体前，必须先把对应目录加入 `resources.local_access.allowed_paths`：

```yaml
plugins:
  htmlrender:
    provider: takumi
    resources:
      local_access:
        allowed_paths:
          - templates
          - assets
```

!!! warning "路径与符号链接校验"
    每次读取本地文件（包括 Jinja2 模板里的 `include`、`extends`、`import`）都会解析真实路径并校验符号链接，防止通过软链跳出白名单目录。

    如果在模板变量里传入相对 `Path`，它会以模板目录为基准解析；若文件位于同级的 `assets/` 目录，请传入 `.resolve()` 后的绝对路径。

## 样式与图片：Takumi 与 Playwright 的差异

不同引擎对外部样式和图片的处理方式不同，写模板时请留意以下区别：

=== "Takumi（推荐写法）"

    - **样式**：Takumi **不支持** `<link rel="stylesheet">`、CSS `@import` 与 `@font-face`。请在 Jinja2 中直接内联样式：

      ```html
      <style>{% include "style.css" %}</style>
      ```

    - **本地图片**：支持相对路径或 `file:` URL（需在白名单内并启用资源处理，插件会直接把图片字节传给 Takumi，不产生临时文件）。
    - **远程图片**：Takumi 不会在排版时自动发起网络请求。需要先通过 `ResourceAccess.fetch_bytes()` 下载，再以字节变量或 `PreparedAsset` 传入。

=== "Playwright"

    - **样式**：完整支持 `<link rel="stylesheet">`、`@import`、`@font-face` 等浏览器标准写法。
    - **本地图片**：由插件按配置策略（内存拦截、`file://` 或内置 Filehost）提供给浏览器，详见 [Playwright 资源传递策略](../configuration/playwright.md#resource-delivery)。
    - **远程图片**：在托管渲染中，所有 HTTP(S) 资源请求都会经由 Bot 侧的受控网络层代为拉取，自动受域名白名单和内网防护策略约束。

## 显式读取与托管资源：`ResourceAccess`

如果业务需要主动拉取本地文件、Python 包内文件或远程图片，可以注入 `ResourceAccess`：

```python
from pathlib import Path

from entari_plugin_htmlrender.resources import (
    FileResourceRef,
    PackageResourceRef,
    RemoteResourceRef,
    ResourceAccess,
)


async def load_assets(resources: ResourceAccess):
    # 读取本地白名单内的文件
    banner = await resources.fetch_bytes(FileResourceRef(Path("assets/banner.png")))

    # 读取 Python 包内附带的资源
    icon = await resources.fetch_bytes(
        PackageResourceRef("my_plugin", "assets/icon.png")
    )

    # 读取远程图片（受 remote_access 域名和内网策略保护）
    avatar = await resources.fetch_bytes(
        RemoteResourceRef("https://cdn.example.com/avatar.png"),
        refresh=False, # 设为 True 可强制重新校验缓存
    )
    return banner, icon, avatar
```

### 临时发布内存资源（`publish`）

当你在使用远程 Playwright 并启用了 Filehost 时，可以通过 `resources.publish()` 把内存中的图片或数据临时发布为一个带租约的 URL：

```python
from entari_plugin_htmlrender.resources import InlineResource, ResourceAccess


async def publish_temp_image(resources: ResourceAccess, png_bytes: bytes):
    async with resources.publish(
        InlineResource(data=png_bytes, media_type="image/png"),
        suffix=".png",
    ) as published:
        # published.url 和 published.request_headers 仅在 async with 块内有效
        ...
```

退出 `async with` 后，该临时资源会自动失效并回收；请勿在块外继续使用 `published.url`，也不要将 `published.request_headers` 复用到其他地址。

## 控制资源处理严格度：`ResourceMaterializationPolicy`

调用 `rasterize_*` 或 `prepare_*` 时，可通过 `materialization_policy` 参数指定资源解析与内联/托管的策略：

| 策略 | 行为说明 | 适用场景 |
| --- | --- | --- |
| `ResourceMaterializationPolicy.AUTO` | 默认策略：自动处理可读取的资源，遇到无法读取或未授权的引用时容忍跳过 | 大多数常规渲染场景 |
| `ResourceMaterializationPolicy.STRICT` | 严格模式：任意资源读取或授权失败立即抛出 `ResourceError` | 要求图片/样式绝不能缺失的关键卡片 |
| `ResourceMaterializationPolicy.OFF` | 关闭处理：不做任何资源抓取、内联或发布 | 纯内联内容，追求极致开销控制 |
