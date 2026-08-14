---
title: 模板与资源
description: TemplateRef、ResourceRef、受控本地路径与 scoped publication
---

# 模板与资源

把模板与静态资源放在受控目录，并将最小目录加入`resources.local_access.allowed_paths`：

```yaml
plugins:
  htmlrender:
    provider: playwright
    resources:
      local_access:
        allowed_paths: [templates, assets]
```

```python
from pathlib import Path

from entari_plugin_htmlrender import HtmlRenderer, TemplateRef
from entari_plugin_htmlrender.resources import FileResourceRef

async def render_card(renderer: HtmlRenderer, name: str):
    return await renderer.rasterize_template(
        TemplateRef(Path("templates"), "card.html"),
        {
            "name": name,
            "logo": FileResourceRef(Path("assets/logo.png")),
        },
    )
```

`TemplateRef.root` 和 HTML `<base>` 只影响相对引用解析，不会扩大访问白名单。locator 使用 `FileResourceRef` / `PackageResourceRef` / `RemoteResourceRef`；payload使用 `ResourceContent` / `InlineResource`，避免按字符串或 `Path` 的形状猜测语义。

需要把 payload 交给必须 fetch URL 的 consumer 时，通过 `ResourceAccess.publish()`建立显式 lease。`PublishedResource` 的 URL 与请求头只在 `async with` 内有效，不能返回 URL 后再使用。

对不可信文档可在 rasterize 调用传入`ResourceMaterializationPolicy.STRICT`，让不可解析资源确定性失败。自定义 Jinja
filter 应使用稳定名称与稳定 callable identity；动态创建匿名函数会扩大 environment
cache key 并降低 compiled-template cache 命中率。
