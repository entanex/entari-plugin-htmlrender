---
title: Preparation 与资源 API
description: parse_html、异步 preparation 与资源解析
---

# Preparation 与资源 API

## 同步 HTML 解析

`parse_html(html, *, base_url=None)` 是同步纯函数，也是 markup 结构解析的唯一入口：

```python
from entari_plugin_htmlrender import parse_html

prepared = parse_html("<base href='/assets/'><main>Hello</main>")
assert prepared.html.startswith("<base")
```

结果 `PreparedHtml` 固化原始 HTML、stylesheets、assets、requirements、`DocumentBase` 与 `DocumentStructureSnapshot`。执行器不得重新解析 markup 推导 base。每个 `PreparedStylesheet` 保存 CSS 与自己的 base；`RenderRequirement` 表示脚本、浏览器布局等执行要求。

## 需要 runtime 的 preparation

`prepare_text`、`prepare_markdown` 与 `prepare_template` 可能读取文件或使用模板environment，因此是异步函数并接收 `runtime=`。已准备的内容可交给`rasterize_html(prepared, runtime=...)`。

## 资源解析

`resolve_template_vars` 递归解析模板变量；`resolve_resource_url` 处理单个`str | Path | bytes`：

```python
from entari_plugin_htmlrender import RuntimeSource, resolve_resource_url

async def publish_logo(runtime: RuntimeSource, data: bytes) -> str:
    result = await resolve_resource_url(data, runtime=runtime)
    return result.value
```

两者返回 `ResourceResolution[T]`。`request_headers_by_url` 只授权映射中的精确URL，不得扩展到同一 host、路径前缀或重定向目标。`strict`、`template_base` 和自定义 `resolver` 均是显式调用参数。
