---
title: Entari 0.2 能力概览与升级
description: Python 与 Entari 基线、0.1 升级步骤、0.2 公共能力与 Takumi 0.4
---

# Entari 0.2 能力概览与升级

`0.2.0` 是一套面向 Entari `0.19.x` 的 provider-neutral 渲染能力。最低环境为 Python `>=3.11,<4.0` 与 Entari `>=0.19.4,<0.20.0`，运行时组合、DI 与生命周期由当前 Entari plugin scope 拥有。

## 从 0.1 升级

静态内容可以安装 Takumi，并将 `plugins.htmlrender.provider` 设为 `takumi`，移除 Playwright 专属的 `provider_config` 后按需配置字体：

```bash
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"
```

Takumi 不执行 JavaScript，HTML/CSS 支持也不等同于浏览器。迁移现有模板前请检查排版结果；中文等字符需按 [Takumi 字体配置](../configuration/providers/takumi.md#fonts)随部署提供字体。使用网页导航、选择器截图或 Markdown 数学公式的业务应保留 `[playwright]` 客户端，改为连接[远程浏览器](../configuration/remote-playwright.md)。

!!! warning "本地 Playwright 弃用计划"

    本地 Playwright 浏览器安装、管理与启动将在不久的将来弃用，后续仅保留 remote support。当前版本仍支持本地模式，尚未确定移除版本或日期。远程连接通过 `connect_ws` 或 `connect_cdp` 配置，Bot 环境不需要执行 `playwright install`；浏览器二进制与系统依赖由远程服务管理。仍使用本地模式时，升级 Playwright 客户端后应重新安装与之匹配的浏览器。

按实际能力选择 `takumi`、`playwright`、`pillow`、`skia`、`filehost`、`sentry` 或 `prometheus` extra。`0.1.0` 使用 Python 3.10 与较早的 Entari 基线；升级到 `0.2.x` 时必须同步调整 Python 与 Entari。

`HtmlRenderService` 现提供 `preparation`、`renderer`、`templates`、`resources`、`graphics`、`drawings` 与 `capabilities` 七个稳定入口。新增 `.preparation: HtmlPreparer` 后，可以在没有 HTML Provider 的 core 安装中生成 `PreparedHtml`，再把同一对象交给 `rasterize_prepared()`。

## 0.2 能力

| 能力 | Public entry | 契约重点 |
| --- | --- | --- |
| Preparation | `service.preparation` / `HtmlPreparer` | `prepare_html`、`prepare_text`、`prepare_markdown`、`prepare_template` 返回中立 `PreparedHtml` |
| HTML rasterization | `service.renderer` / `HtmlRenderer` | 显式 `RasterOptions`、typed result、统一 admission 与资源策略 |
| Template | `service.templates` / `TemplateRenderer` | `TemplateRef`、变量、可选 filters 与 extensions |
| Resources | `service.resources` / `ResourceAccess` | 显式 `ResourceRef`、精确 URL 授权、cache 与 publication lease |
| Playwright | `capabilities.playwright` | managed page/browser lease；远程 CDP/WS 与文件资源传输 |
| Takumi | `capabilities.takumi` | 要求 `takumi-py>=0.4.0`；HTML/compiled/node/SVG/animation/font 操作，另保留 raw renderer lease |
| Graphics | `service.graphics` / `GraphicsRenderer` | Pillow 与 Skia 共享 `RasterScene` contract，可同时启用 |
| Drawing | `service.drawings` / `DrawingRenderer` | 按配置名称执行受信任的 Pillow/Skia 原生 Python 绘图函数 |
| Provider SDK | `entari_plugin_htmlrender.providers.v2` | 独立的发现、availability、resource strategy 与 composition 契约 |

Playwright 适合浏览器布局、JavaScript、导航与 selector 截图；Takumi 适合不依赖浏览器语义的静态 HTML、SVG、动画与动态字体。Pillow/Skia 同时支持两条独立的绘图路径：`GraphicsRenderer` 执行 backend-neutral `RasterScene`，`DrawingRenderer` 执行按名称配置且可直接调用 Pillow/Skia 原生 API 的 Python 函数。两者都不属于 HTML Provider。完整配置与安全边界见[绘图后端](../configuration/graphics/index.md)。

## Markdown 数学兼容变化

0.2 的 Arithmatex 管线固定使用 `generic=True`、`smart_dollar=True`。行内 `$x$` 与 `\(x\)` 受支持；`$ x $` 的美元与内容之间有空白，新管线会保留为原文，而 0.1 公式管线可能把它识别为公式。这是为货币和宽松美元写法提供明确边界的兼容变化；需要公式时应使用紧贴内容的 `$x$`。

块级 `$$...$$` 与 `\[...\]` 必须独占段落或进入块解析，独立的 `\begin{env}...\end{env}` 也受支持。0.1 实现可能把同一段落中的 `before $$x$$ after` 识别为 display math；新管线不承诺这种语义，需要块级展示时应迁移为独立段落。

Arithmatex 生成的公式容器使用公开的 `.arithmatex` class，并带有内部 `data-htmlrender-arithmatex` 标记。KaTeX 初始化脚本只处理带该标记的解析器输出，不扫描没有标记的原始 HTML `.arithmatex` 容器；inline raw HTML 中的普通 Markdown 仍可能被解析。公式 preparation 可以成功，但会注入 JavaScript 并设置 `DocumentRequirement.JAVASCRIPT`。Playwright 可以执行；Takumi rasterization 会以 `UnsupportedDocumentFeatureError` 拒绝该文档，不会生成静态公式图像。

## DI 与生命周期

业务 handler 可以直接注入 `HtmlRenderer`、`TemplateRenderer`、`HtmlPreparer`、`ResourceAccess`、`GraphicsRenderer` 或 `DrawingRenderer`。需要多个入口时仍可注入 concrete `HtmlRenderService`。这些对象均绑定当前 plugin lifetime，不应保存在模块级全局变量中。

配置变化通过 Entari 默认的 staged reload 重建 composition；导入、配置校验和 composition 失败会保留旧插件。promote 后的 service startup/probe 失败不会回滚已经 promote 的插件，详见 [Runtime 生命周期](../reference/runtime.md)。Launart 的 `preparing` 与 `cleanup` 负责启动、停止接纳、排空与关闭；不要手工驱动 service 内部 runtime。

`graphics.backend: pillow` 选择默认图形入口。需要同时使用 Pillow 和 Skia 时设置：

```yaml
plugins:
  htmlrender:
    graphics:
      backends: [pillow, skia]
      backend: pillow
```

`backend` 必须出现在 `backends` 中；省略时使用首项作为 `service.graphics`。独立后端仍可通过 `service.capabilities.pillow` 与 `.skia` 调用。`service.drawings` 与 `service.graphics` 指向不同的领域入口；前者按名称加载受信任 Python 代码，后者执行可序列化的 `RasterScene`。两条路径共用 `graphics.max_pixels` 与 `graphics.max_concurrency`，但 `graphics.max_commands` 只限制 `RasterScene.commands`。

## Takumi 0.4 managed API

`[takumi]` extra 要求 `takumi-py>=0.4.0`，不设上限。`TakumiSession` 保留小型调用面；`capabilities.takumi.lease_api()` 另行提供完整高级 API，包括 compile、measure、HTML/node/SVG、animation、frame 与 font 操作。`TakumiCompiledDocument` 是本插件的稳定 lease-scoped 包装，承载 native compiled node/stylesheets；managed session、API 与 compiled document 都只在对应 lease 内有效，需要保留到上下文外的代码应把操作移回 `async with` 内。

### Font subsets、cache 与 release

配置中的 `fonts[].unicode_range` 与 `register_font_file(..., unicode_range=...)` 都接受闭区间码位列表，例如 `((0x0000, 0x007F),)`。同一字体族的子集文件应使用相同 `name`，并分别声明 `unicode_range`，让 Takumi 按字符选择覆盖该码位的文件。`subset_of` 作为兼容入口仍可读取，但上游已将相应 native 参数标记为弃用；新配置和代码应迁移到 `name` + `unicode_range`。

`lease_api()` 提供 `cache_font(font, key)`、`cached_fonts(key, pin=False)`、`unregister_font(name)` 与 `clear_fonts()`。`register_font*` 注册的字体在 runtime 内保持 pinned，直到显式释放；`cache_font()` 的条目可按来源 key 查询并受空间淘汰，`pin=True` 可将其转为 pinned。

`provider_config.cache_max_bytes` 控制 native resource cache，`null` 使用上游 64 MiB 默认值，`0` 禁止保留。`provider_config.font_cache_max_bytes` 控制 `cache_font()` 的淘汰预算，`null` 表示无上限；它不是严格的进程内存峰值上限，且 pinned 字体不参与空间释放。字段、调优与诊断见 [Takumi 配置](../configuration/providers/takumi.md)和[缓存生命周期](../guides/cache-lifecycle.md)。

### Animation FPS

`takumi-py` 0.4.0 的 native 编码器限制帧率：WebP 与 APNG 不得超过 `90` fps，GIF 不得超过 `50` fps。插件传递 `fps` 参数，并将上游失败转换为 `ProviderExecutionError`；这些上限由上游校验，插件不自行截断或降帧。

### 插件接入边界

插件当前未接入上游 `Document`、`RasterImage` 与 MathJax API。上文 `TakumiCompiledDocument` 是本插件的稳定包装，不能据此假定公开了上游 `Document`。单独升级 `takumi-py` 不会改变插件的公式管线：Markdown 公式仍通过 KaTeX JavaScript 渲染，需要 Playwright；Takumi 会以 `UnsupportedDocumentFeatureError` 拒绝含 JavaScript 要求的文档。需要静态后端输出公式时，应先提供不依赖 JavaScript 的预排版 HTML/SVG。

原生 Playwright 与 Takumi 类型只用于静态检查。普通 core import 不会加载浏览器、native engine 或对应可选依赖。

## 扩展实现者

第三方 Provider 在 `entari_plugin_htmlrender.providers.v2` entry-point group 注册，并实现 `RenderProvider` 契约。直接构造 `RenderRuntime` 的高级 embedding 需要传入 `preparer: HtmlPreparer`；使用 `build_runtime_plan()` 或 `runtime.composition.build_runtime()` 时无需手动接线。

实现 `HtmlPreparer`、`TemplateRenderer` 或 `HtmlRenderer` 的替身需要支持模板操作新增的 `filters` 与 `extensions` 关键字参数。普通调用方不传这些参数时行为保持不变。异常聚合使用 Python 3.11 标准库的 `ExceptionGroup` / `BaseExceptionGroup`，原有稳定错误层级和结构化字段继续保留。

当前发布面保持独立 Entari library/plugin 边界，不提供面向其他宿主框架的迁移 shim，也不通过可选 backend 引入宿主框架插件依赖。
