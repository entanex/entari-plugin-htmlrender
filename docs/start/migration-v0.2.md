---
title: Entari 0.2 能力概览与升级
description: Python 与 Entari 基线、0.1 升级步骤和 0.2 公共能力
---

# Entari 0.2 能力概览与升级

`0.2.0` 是一套面向 Entari `0.19.x` 的 provider-neutral 渲染能力。最低环境为 Python `>=3.11,<4.0` 与 Entari `>=0.19.4,<0.20.0`，运行时组合、DI 与生命周期由当前 Entari plugin scope 拥有。

## 从 0.1 升级

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.2.0,<0.3"
uv run playwright install chromium
```

按实际能力选择 `playwright`、`takumi`、`pillow`、`skia`、`filehost`、`sentry` 或 `prometheus` extra。升级 Playwright client 后，需要在同一环境中重新安装浏览器。`0.1.0` 使用 Python 3.10 与较早的 Entari 基线；升级到 `0.2.x` 时必须同步调整 Python 与 Entari。

原有 `HtmlRenderService.renderer`、`.templates`、`.resources`、`.graphics` 与 `.capabilities` 入口保持可用。新增 `.preparation: HtmlPreparer` 后，可以在没有 HTML Provider 的 core 安装中生成 `PreparedHtml`，再把同一对象交给 `rasterize_prepared()`。

## 0.2 能力

| 能力 | Public entry | 契约重点 |
| --- | --- | --- |
| Preparation | `service.preparation` / `HtmlPreparer` | `prepare_html`、`prepare_text`、`prepare_markdown`、`prepare_template` 返回中立 `PreparedHtml` |
| HTML rasterization | `service.renderer` / `HtmlRenderer` | 显式 `RasterOptions`、typed result、统一 admission 与资源策略 |
| Template | `service.templates` / `TemplateRenderer` | `TemplateRef`、变量、可选 filters 与 extensions |
| Resources | `service.resources` / `ResourceAccess` | 显式 `ResourceRef`、精确 URL 授权、cache 与 publication lease |
| Playwright | `capabilities.playwright` | managed page/browser lease；远程 CDP/WS 与文件资源传输 |
| Takumi | `capabilities.takumi` | HTML/compiled/node/SVG/animation/font 操作，另保留 raw renderer lease |
| Graphics | `service.graphics` / `GraphicsRenderer` | Pillow 与 Skia 共享 `RasterScene` contract，可同时启用 |
| Provider SDK | `entari_plugin_htmlrender.providers.v2` | 独立的发现、availability、resource strategy 与 composition 契约 |

Playwright 适合浏览器布局、JavaScript、导航与 selector 截图；Takumi 适合不依赖浏览器语义的静态 HTML、SVG、动画与动态字体。Pillow/Skia 只实现独立的 `RasterScene` 图形契约，不属于 HTML Provider。

## Markdown 数学兼容变化

0.2 的 Arithmatex 管线固定使用 `generic=True`、`smart_dollar=True`。行内 `$x$` 与 `\(x\)` 受支持；`$ x $` 的美元与内容之间有空白，新管线会保留为原文，而 0.1 公式管线可能把它识别为公式。这是为货币和宽松美元写法提供明确边界的兼容变化；需要公式时应使用紧贴内容的 `$x$`。

块级 `$$...$$` 与 `\[...\]` 必须独占段落或进入块解析，独立的 `\begin{env}...\end{env}` 也受支持。0.1 实现可能把同一段落中的 `before $$x$$ after` 识别为 display math；新管线不承诺这种语义，需要块级展示时应迁移为独立段落。

Arithmatex 生成的公式容器使用公开的 `.arithmatex` class，并带有内部 `data-htmlrender-arithmatex` 标记。KaTeX 初始化脚本只处理带该标记的解析器输出，不扫描没有标记的原始 HTML `.arithmatex` 容器；inline raw HTML 中的普通 Markdown 仍可能被解析。公式 preparation 可以成功，但会注入 JavaScript 并设置 `DocumentRequirement.JAVASCRIPT`。Playwright 可以执行；Takumi rasterization 会以 `UnsupportedDocumentFeatureError` 拒绝该文档，不会生成静态公式图像。

## DI 与生命周期

业务 handler 可以直接注入 `HtmlRenderer`、`TemplateRenderer`、`HtmlPreparer`、`ResourceAccess` 或 `GraphicsRenderer`。需要多个入口时仍可注入 concrete `HtmlRenderService`。这些对象均绑定当前 plugin lifetime，不应保存在模块级全局变量中。

配置变化通过 Entari 默认的 staged reload 重建 composition；导入、配置校验和 composition 失败会保留旧插件。promote 后的 service startup/probe 失败不会回滚已经 promote 的插件，详见 [Runtime 生命周期](../reference/runtime.md)。Launart 的 `preparing` 与 `cleanup` 负责启动、停止接纳、排空与关闭；不要手工驱动 service 内部 runtime。

`graphics.backend: pillow` 选择默认图形入口。需要同时使用 Pillow 和 Skia 时设置：

```yaml
plugins:
  htmlrender:
    graphics:
      backends: [pillow, skia]
      backend: pillow
```

`backend` 必须出现在 `backends` 中；省略时使用首项作为 `service.graphics`。独立后端仍可通过 `service.capabilities.pillow` 与 `.skia` 调用。

## Takumi managed API

`TakumiSession` 保留原来的三个操作。`capabilities.takumi.lease_api()` 另行提供完整高级 API，包括 compile、measure、HTML/node/SVG、animation、frame 与 font 操作。managed session、API 与 compiled document 只在对应 lease 内有效；需要保留到上下文外的代码应把操作移回 `async with` 内。

原生 Playwright 与 Takumi 类型只用于静态检查。普通 core import 不会加载浏览器、native engine 或对应可选依赖。

## 扩展实现者

第三方 Provider 在 `entari_plugin_htmlrender.providers.v2` entry-point group 注册，并实现 `RenderProvider` 契约。直接构造 `RenderRuntime` 的高级 embedding 需要传入 `preparer: HtmlPreparer`；使用 `build_runtime_plan()` 或 `runtime.composition.build_runtime()` 时无需手动接线。

实现 `HtmlPreparer`、`TemplateRenderer` 或 `HtmlRenderer` 的替身需要支持模板操作新增的 `filters` 与 `extensions` 关键字参数。普通调用方不传这些参数时行为保持不变。异常聚合使用 Python 3.11 标准库的 `ExceptionGroup` / `BaseExceptionGroup`，原有稳定错误层级和结构化字段继续保留。

当前发布面保持独立 Entari library/plugin 边界，不提供面向其他宿主框架的迁移 shim，也不通过可选 backend 引入宿主框架插件依赖。
