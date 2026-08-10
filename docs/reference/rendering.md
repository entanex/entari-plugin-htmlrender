---
title: 渲染 API
description: caller-first 便利函数、HtmlRenderer、typed request、artifact 与错误
---

# 渲染 API

## Caller-first 函数

所有便利函数都把主要输入放在首位，并以 kw-only `runtime=` 接收`RuntimeSource`：

| 函数 | 返回值 |
| --- | --- |
| `render_html(html, ...)` | `RenderedImage` |
| `render_text(text, ...)` | `RenderedImage` |
| `render_markdown(markdown, ...)` | `RenderedImage` |
| `render_template(path, name, variables, ...)` | `RenderedImage` |
| `render_template_html(path, name, variables, ...)` | `RenderedHtml` |
| `rasterize_html(prepared, options, ...)` | `RenderedImage` |

```python
from entari_plugin_htmlrender import RuntimeSource, render_markdown

async def render_readme(runtime: RuntimeSource, source: str) -> bytes:
    image = await render_markdown(source, width=720, runtime=runtime)
    return bytes(image)
```

## Typed request 与 HtmlRenderer

需要复用 request 或先探测命令时，从 runtime 取得 `HtmlRenderer`：

```python
from entari_plugin_htmlrender import (
    RasterOptions,
    RenderHtmlRequest,
    RuntimeSource,
    resolve_runtime,
)
from entari_plugin_htmlrender.rendering import RenderCommand

async def render_request(runtime: RuntimeSource) -> bytes:
    renderer = resolve_runtime(runtime).renderer
    if not renderer.supports(RenderCommand.HTML):
        raise RuntimeError("HTML command is unavailable")
    image = await renderer.render_html(RenderHtmlRequest("<h1>Hello</h1>", RasterOptions(width=640)))
    return bytes(image)
```

`supported_commands` 是 `frozenset[RenderCommand]`；字符串不是合法探测参数。

## Artifact 与错误

`RenderedImage` 保存编码字节、format、width 与 height；`bytes(image)` 显式取得payload。`RenderedHtml` 保存规范 HTML 字符串。

公共错误均继承 `RenderingError`。常用边界包括 `InvalidRenderRequest`、`UnsupportedRenderOption`、`UnsupportedRequirement`、`CapabilityUnavailable`、`ProviderUnavailable`、`ProviderExecutionError`、`ProviderLifecycleError`、`ResourceResolutionError` 与`RuntimeNotBound`。业务分支应匹配稳定错误类型，不要解析底层异常文本。

完整 request 类型包括 `RenderTextRequest`、`RenderMarkdownRequest`、`RenderTemplateRequest`、`RenderTemplateHtmlRequest` 与 `RasterizeHtmlRequest`；图片格式使用 `RasterImageFormat`。`PreparationError` 表示内容准备失败，`ErrorCause`是经过裁剪的底层原因快照。
