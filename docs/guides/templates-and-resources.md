---
title: 模板与资源
description: TemplateRef、ResourceRef、受控本地路径与 scoped publication
icon: lucide/files
---

# 模板与资源

下面使用 Takumi 渲染静态模板。把模板与静态资源放在受控目录，并将最小目录加入 `resources.local_access.allowed_paths`：

```yaml
plugins:
  htmlrender:
    provider: takumi
    resources:
      local_access:
        allowed_paths: [templates, assets]
```

中文等字符需要额外配置字体，见 [Takumi 字体配置](../configuration/providers/takumi.md#fonts)。模板依赖 JavaScript 或浏览器专属布局时，使用[远程 Playwright](../configuration/remote-playwright.md)。

```python
from pathlib import Path

from entari_plugin_htmlrender import HtmlRenderer, TemplateRef

async def render_card(renderer: HtmlRenderer, name: str):
    return await renderer.rasterize_template(
        TemplateRef(Path("templates"), "card.html"),
        {
            "name": name,
            "logo": Path("assets/logo.png").resolve(),
        },
    )
```

在模板中用 `<img src="{{ logo }}">` 引用图片。启用资源物化时，模板变量支持 `Path` 和字节数据；相对 `Path` 以模板根目录为基准，所以示例先用 `.resolve()` 明确工作目录下的 `assets` 路径。`TemplateRef.root` 和 HTML `<base>` 只影响相对引用解析，不会扩大访问白名单。

显式调用 `ResourceAccess` 时，locator 使用 `FileResourceRef` / `PackageResourceRef` / `RemoteResourceRef`，payload 使用 `ResourceContent` / `InlineResource`；这些对象不是模板图片变量的替代写法。远程图片应先用资源接口读取，再把字节作为变量交给模板。

Takumi 不支持 `<link rel="stylesheet">`、CSS `@import` 或 `@font-face`。Jinja2 模板可以使用 `<style>{% include "style.css" %}</style>` 内联样式，字体通过 Provider 配置或能力接口注册；完整示例位于仓库的 `examples/template_render`。

需要把 payload 交给必须 fetch URL 的 consumer 时，通过 `ResourceAccess.publish()`建立显式 lease。`PublishedResource` 的 URL 与请求头只在 `async with` 内有效，不能返回 URL 后再使用。

对不可信文档可在 rasterize 调用传入`ResourceMaterializationPolicy.STRICT`，让不可解析资源确定性失败。自定义 Jinja
filter 应使用稳定名称与稳定 callable identity；动态创建匿名函数会扩大 environment
cache key 并降低 compiled-template cache 命中率。

## 自定义过滤器与扩展 { #template-customization }

`rasterize_template()`、`templates.render()`、`preparation.prepare_template()` 和 `preparation.render_template()` 接受相同的 `filters` 与 `extensions` 关键字参数。它们只作用于本次调用选择的 Jinja environment，默认保持 autoescape，缓存按模板根目录、扩展及 callable identity 隔离。

```python
from pathlib import Path

from entari_plugin_htmlrender import TemplateRef, TemplateRenderer

def badge(value: str) -> str:
    return f"[{value.upper()}]"

async def render_badge(templates: TemplateRenderer):
    return await templates.render(
        TemplateRef(Path("templates"), "badge.html"),
        {"name": "Entari"},
        filters={"badge": badge},
        extensions=("jinja2.ext.do",),
    )
```

模板中可使用 `{{ name | badge }}`，或在启用 `jinja2.ext.do` 后使用 `{% do ... %}`。`TemplateRef` 仍只保存模板位置；扩展不是模板路径的一部分。过滤器必须是可调用对象，扩展必须是导入路径或 `jinja2.ext.Extension` 子类；无效参数会得到带 `field` 的 `InvalidRenderInputError`。
