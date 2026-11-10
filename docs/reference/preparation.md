---
title: Preparation 与资源 API
description: HtmlPreparer、PreparedHtml、ResourceAccess 与 scoped publication
---

# Preparation 与资源 API

`HtmlPreparer` 把 HTML、文本、Markdown 或模板转换为与渲染后端无关的 `PreparedHtml`。Entari service 通过 `service.preparation` 暴露这个 contract；调用方也可以让框架无关函数直接接收根包导出的 `HtmlPreparer`。

```python
from entari_plugin_htmlrender import HtmlPreparer, RasterOptions
from entari_plugin_htmlrender.entari import HtmlRenderService

async def prepare_and_render(service: HtmlRenderService):
    prepared = await service.preparation.prepare_markdown(
        "# Hello\n\nPrepared once, rendered through the selected Provider.",
    )
    return await service.renderer.rasterize_prepared(
        prepared,
        raster=RasterOptions(width=720),
    )
```

分离 preparation 与 rasterization 适合需要检查或传递中立文档、缓存同一 `PreparedHtml`，或把 preparation 与执行放在不同业务步骤中的调用方。`rasterize_markdown()`、`rasterize_text()` 与 `rasterize_template()` 是 convenience methods，内部完成相同准备步骤后再交给当前 Provider。

## HtmlPreparer

| 方法 | 输入与输出 |
| --- | --- |
| `prepare_html(html, *, base_url=None)` | inline HTML → `PreparedHtml` |
| `prepare_text(text, *, stylesheet=None)` | 文本与可选 stylesheet → `PreparedHtml` |
| `prepare_markdown(source, *, stylesheet=None, materialization_policy=None)` | inline `str` 或显式 `ResourceRef` → `PreparedHtml` |
| `prepare_template(template, variables, *, materialization_policy=None)` | `TemplateRef` 与变量 mapping → `PreparedHtml` |
| `render_template(template, variables)` | `TemplateRef` 与变量 mapping → 原始 HTML `str` |

所有方法都是 async，并使用当前 runtime 的资源 access、template compiler、worker 与 admission boundary。不要把 `DefaultHtmlPreparer` 当作普通 caller type；业务代码依赖 `HtmlPreparer`，由 Entari DI 或 composition 提供具体实现。

### prepare_html

`prepare_html()` 保留 inline markup 与调用方声明的 `base_url`，解析一次并固化 `DocumentBase`、stylesheet、assets、requirements 与结构快照。它是异步边界，但不自动物化文档引用：

```python
from entari_plugin_htmlrender import HtmlPreparer, PreparedHtml

async def prepare_document(preparer: HtmlPreparer) -> PreparedHtml:
    return await preparer.prepare_html(
        '<main><img src="logo.png">Hello</main>',
        base_url="https://example.com/cards/",
    )
```

`base_url` 必须由调用方明确提供；不要从 HTML 字符串形状、调用路径或进程工作目录猜测来源。

### prepare_text

`prepare_text()` 对文本做 HTML 转义，并使用内置 text template。传入 `stylesheet=FileResourceRef(...)`、`PackageResourceRef(...)` 或 `RemoteResourceRef(...)` 可替换默认 CSS；stylesheet 仍经过资源策略与大小限制。

```python
from pathlib import Path

from entari_plugin_htmlrender import HtmlPreparer
from entari_plugin_htmlrender.resources import FileResourceRef

async def prepare_note(preparer: HtmlPreparer):
    return await preparer.prepare_text(
        "<script>alert(1)</script>",
        stylesheet=FileResourceRef(Path("assets/note.css")),
    )
```

文本中的标签保持字面量，不会被解释为 markup。

### prepare_markdown

`prepare_markdown()` 的 `source` 有两种明确形态：

- Python `str` 始终是 inline Markdown，即使字符串恰好像文件路径；
- 文件、package 或远端文档必须使用对应 `ResourceRef`。

```python
from pathlib import Path

from entari_plugin_htmlrender import HtmlPreparer, ResourceMaterializationPolicy
from entari_plugin_htmlrender.resources import FileResourceRef

async def prepare_readme(preparer: HtmlPreparer):
    return await preparer.prepare_markdown(
        FileResourceRef(Path("README.md")),
        materialization_policy=ResourceMaterializationPolicy.STRICT,
    )
```

内置 pipeline 支持表格、fenced code、任务列表、数学公式与常见 Markdown 扩展，并注入与文本相同方式的 stylesheet。`materialization_policy` 覆盖本次 preparation 的资源默认策略；未提供时使用当前 composition 的资源策略。

数学公式由 `pymdownx.arithmatex` 的 `generic=True`、`smart_dollar=True` 配置解析，支持以下 TeX 分隔符：

- 行内公式：`$x$`、`\(x\)`
- 块级公式：`$$...$$`、`\[...\]`、独立的 `\begin{env}...\end{env}`

`smart_dollar=True` 要求行内公式的 `$` 与内容边界紧邻；`$ x $` 不会被识别为公式并保持原文。块级 `$$...$$` 与 `\[...\]` 必须独占段落或进入块解析；同一段落中的 `before $$x$$ after` 不提供块级展示语义，需要迁移为独立段落。

Generic 模式把识别出的公式统一保存为带 `arithmatex` class 的 `\(...\)` 或 `\[...\]` TeX 标记，不在 Python preparation 阶段求值。Treeprocessor 另外给实际生成的容器添加内部 `data-htmlrender-arithmatex` 标记；KaTeX 初始化脚本只选择 `.arithmatex[data-htmlrender-arithmatex]`，不扫描整页，也不处理没有该属性的原始 HTML `.arithmatex` 容器。Inline raw HTML 中的普通 Markdown 仍可能被解析，因此不要依赖手写 wrapper 阻止公式识别。

公式 preparation 可以成功完成并返回 `PreparedHtml`，但会注入 KaTeX 脚本并把 `DocumentRequirement.JAVASCRIPT` 加入文档要求。Playwright 可执行该脚本；Takumi 在 rasterization 的 source inspection 阶段以 `UnsupportedDocumentFeatureError`（`feature="javascript"`）拒绝文档，不会继续生成图像。代码 span 与 fenced code 中的分隔符保持字面量，也不会被容器级初始化脚本改写。

### prepare_template

`prepare_template()` 通过当前 `TemplateRef` 渲染 Jinja 模板，把 template output 解析为同一个 `PreparedHtml`。模板目录必须在 `resources.local_access.allowed_paths` 中；相对模板资源按模板目录解析。

```python
from pathlib import Path

from entari_plugin_htmlrender import HtmlPreparer, TemplateRef

CARD = TemplateRef(Path("templates"), "card.html")

async def prepare_card(preparer: HtmlPreparer, name: str):
    return await preparer.prepare_template(CARD, {"name": name})
```

变量 mapping 在调用边界取得浅快照，调用方后续修改原 mapping 不会改变正在执行的这个操作。模板到 artifact 的普通入口仍是 `service.templates.render()`；`prepare_template()` 的职责是继续生成可供 Provider 执行的 `PreparedHtml`。

`render_template()` 与 `prepare_template()` 使用相同模板授权和错误边界，但只返回原始 HTML `str`，不解析 `PreparedHtml`，也不把模板资产物化到可执行文档中。需要 `RenderedHtml` artifact 的普通业务代码应使用 `TemplateRenderer.render()`。

## PreparedHtml

`PreparedHtml` 是 immutable value，不是 runtime handle。它冻结解析得到的文档语义，避免 Provider 在执行阶段重新猜测 base；同一调用方可以在当前 runtime 仍接纳操作时复用它做多次 rasterization。

`PreparedHtml` 还携带 `PreparedStylesheet`、assets、`DocumentRequirement` 与 `DocumentStructureSnapshot`。执行阶段的 `rasterize_prepared()` 不会再次解析 markup 来推导 document base。不要跨已关闭的 service 保存 `HtmlPreparer`、`HtmlRenderer` 或 capability；保存一个纯 value 与保存 host facade 是不同问题，执行仍需当前有效 runtime。

## 纯同步 parse

`parse_html(html, *, base_url=None)` 是不依赖 runtime 的纯同步 HTML → `PreparedHtml` 入口：

```python
from entari_plugin_htmlrender import parse_html

prepared = parse_html(
    "<base href='/assets/'><main>Hello</main>",
    base_url="https://example.com/card/",
)
assert prepared.document_base.resolve() == "https://example.com/assets/"
```

当调用方只需要 canonical parse、没有文本/Markdown 转换或 template I/O 时使用 `parse_html()`。需要共享 resource service、template compiler 或 worker 时使用 `service.preparation`。

## 资源身份

`ResourceRef` 只表示 locator：

- `FileResourceRef(Path(...))`
- `PackageResourceRef(package, name)`
- `RemoteResourceRef(url)`

`ResourceContent` 与 `InlineResource` 只表示 payload。`PublishedResource` 原子携带 URL 与该 URL 必需的精确请求头，并且只在 publication lease 内有效。

每种 `ResourceRef` 与 `InlineResource` 的只读 `.identity` 是规范化 structural identity，可用于 keying/deduplication；它不是 fetch cache 的公开控制面，也不授予访问权限。

```python
from pathlib import Path

from entari_plugin_htmlrender.resources import FileResourceRef, ResourceAccess

async def consume_logo(resources: ResourceAccess) -> None:
    content = await resources.fetch(FileResourceRef(Path("assets/logo.png")))
    async with resources.publish(content, suffix=".png") as published:
        await consume(
            published.url,
            request_headers=published.request_headers,
        )
```

不要在 `async with` 退出后缓存或返回 `published.url`。授权请求头不得扩张到同一 host、路径前缀或重定向目标。

`ResourceAccess` 还提供 `fetch_bytes()` 与 `fetch_text()`；三种 fetch 都只接受 `ResourceRef`，不会把 inline payload 伪装成可读取来源。

## 显式资源解析

`ResourceAccess` 还提供与渲染独立的资源解析入口，均返回 `ResourceResolution[T]`：

| 方法 | 输入 | `value` |
| --- | --- | --- |
| `resolve_template_vars()` | 嵌套变量 mapping | 重写后的变量 `dict` |
| `to_resource_url()` | 路径、字符串或 bytes | 使用配置 transport 得到的 URL |
| `resolve_url_tokens()` | URL 字符串序列 | 保留 query/fragment 的 URL 列表 |

`request_headers_by_url` 是深度冻结的精确请求 URL 到请求头映射。键保留 query，去掉浏览器不会发送的 fragment；返回的 `value` 仍保留 fragment。消费者只能把每组鉴权头应用于它对应的请求 URL，不能扩展到同一 host、其他 query 或重定向目的地。

`resolve_url_tokens()` 在定位本地文件前按 UTF-8 解码 URL path 中的百分号转义，因此 `logo%20one.png` 对应 `logo one.png`。解码后的路径仍通过路径白名单与越界检查。解析操作遵守已有资源预算、物化策略和 runtime admission；未知 materializer 或无效参数会通过稳定错误报告。

```python
from pathlib import Path

from entari_plugin_htmlrender.resources import ResourceAccess

async def prepare_logo_url(resources: ResourceAccess):
    result = await resources.to_resource_url(
        Path("assets/logo.png"),
        strict=True,
        materializer="file",
    )
    return result.value
```

公共 helper 不接收内部 publication lease ID。选择 filehost transport 时，它们返回的是未固定的缓存 URL：`cache_ttl_seconds` 控制复用新鲜度，不保证 URL 存活时间；容量淘汰、缓存清理或 publisher 关闭都可能使 URL 失效。需要确定有效作用域时使用 `resources.publish()`，并让消费者的访问在其 `async with` 内完成。

## Materialization policy

单次 preparation 或 rasterization 可显式覆盖资源物化策略：

```python
from entari_plugin_htmlrender import HtmlRenderer
from entari_plugin_htmlrender.resources import ResourceMaterializationPolicy

async def render_strict(renderer: HtmlRenderer, html: str):
    return await renderer.rasterize_html(
        html,
        materialization_policy=ResourceMaterializationPolicy.STRICT,
    )
```

`off` 不物化文档资源，`auto` 容忍不可解析引用，`strict` 将其报告为结构化资源错误。该 policy 决定一次操作如何处理资源；Provider 的 `ResourceStrategy` 决定 composition 使用哪种 transport，两者职责不同。

## 失败语义

输入类型、`base_url` 形状、`TemplateRef` 与 inline resource payload 会在 admission 边界拒绝，并返回带 `operation`、`field` 的 `InvalidRenderInputError`。资源读取失败使用 `ResourceError` 子类；模板编译或渲染失败会收口为稳定的渲染错误，同时仅通过有界 `ErrorCause` 暴露底层诊断。关闭中的 runtime 会拒绝新的 preparation 调用，等待已经接纳的操作完成后再关闭资源。
