---
title: 模板与资源
description: Jinja 模板、受控本地路径与显式资源解析
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

from entari_plugin_htmlrender import RuntimeSource, render_template

async def render_card(runtime: RuntimeSource, name: str):
    return await render_template(
        Path("templates"),
        "card.html",
        {"name": name, "logo": Path("assets/logo.png")},
        runtime=runtime,
    )
```

`template_base` 和 HTML `<base>` 只影响相对引用解析，不会扩大访问白名单。模板变量中的 `Path`/bytes 可由 Resource Service 递归解析；需要在模板外观察最终值时调用`resolve_template_vars(..., runtime=...)`，单个值调用`resolve_resource_url(..., runtime=...)`。

两者返回 `ResourceResolution`。若 filehost 产生授权 header，只能把`request_headers_by_url[url]` 应用于该精确 URL。对不可信模板使用`ResourcePolicy.STRICT`，让不可解析资源确定性失败。

自定义 Jinja filter 应使用稳定名称与稳定 callable 身份；动态创建匿名函数会扩大environment cache key，并降低 compiled-template cache 命中率。
