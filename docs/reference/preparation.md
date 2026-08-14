---
title: Preparation 与资源 API
description: parse、TemplateRenderer、ResourceAccess 与 scoped publication
---

# Preparation 与资源 API

## 纯同步 parse

`parse_html(html, *, base_url=None)` 是纯同步的 HTML → `PreparedHtml` 入口：

```python
from entari_plugin_htmlrender import parse_html

prepared = parse_html(
    "<base href='/assets/'><main>Hello</main>",
    base_url="https://example.com/card/",
)
assert prepared.document_base.resolve() == "https://example.com/assets/"
```

`PreparedHtml` 固化原始 HTML、`PreparedStylesheet`、assets、requirements、`DocumentBase` 与 `DocumentStructureSnapshot`。执行阶段不得再次解析 markup 推导 base。`DocumentRequirement` 目前标识 JavaScript、网络与本地资源要求。

可能执行 I/O 的 preparation 是内部 application step：文本、Markdown 与模板rasterization 由 `HtmlRenderer` 完整拥有；模板到 HTML 则由 `TemplateRenderer.render()`拥有。普通调用方不拼接 preparer、materializer 与 executor。

## 资源身份

`ResourceRef` 只表示 locator：

- `FileResourceRef(Path(...))`
- `PackageResourceRef(package, name)`
- `RemoteResourceRef(url)`

`ResourceContent` 与 `InlineResource` 只表示 payload。`PublishedResource` 原子携带 URL与该 URL 必需的精确请求头，并且只在 publication lease 内有效。

每种 `ResourceRef` 与 `InlineResource` 的只读 `.identity` 是规范化 structural identity，可用于 keying/deduplication；它不是 fetch cache 的公开控制面，也不授予访问权限。

```python
from pathlib import Path

from entari_plugin_htmlrender.resources import (
    FileResourceRef,
    ResourceAccess,
)

async def consume_logo(resources: ResourceAccess) -> None:
    content = await resources.fetch(FileResourceRef(Path("assets/logo.png")))
    async with resources.publish(content, suffix=".png") as published:
        await consume(
            published.url,
            request_headers=published.request_headers,
        )
```

不要在 `async with` 退出后缓存或返回 `published.url`。授权请求头不得扩张到同一host、路径前缀或重定向目标。

`ResourceAccess` 还提供 `fetch_bytes()` 与 `fetch_text()`；三种 fetch 都只接受`ResourceRef`，不会把 inline payload 伪装成可读取来源。

## Materialization policy

单次 rasterization 可显式覆盖资源物化策略：

```python
from entari_plugin_htmlrender import HtmlRenderer
from entari_plugin_htmlrender.resources import ResourceMaterializationPolicy

async def render_strict(renderer: HtmlRenderer, html: str):
    return await renderer.rasterize_html(
        html,
        materialization_policy=ResourceMaterializationPolicy.STRICT,
    )
```

`OFF` 不物化文档资源，`AUTO` 容忍不可解析引用，`STRICT` 将其报告为结构化资源错误。该 policy 决定一次操作如何处理资源；Provider 的 `ResourceStrategy` 决定composition 使用哪种 transport，两者职责不同。
