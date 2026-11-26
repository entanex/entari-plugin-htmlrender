# 术语表

本页用通俗易懂的方式解释文档与 API 中经常出现的关键概念。

**Provider（HTML 渲染后端）**

负责把准备好的 HTML 真正渲染成图片的引擎实现，例如内置的 **Takumi**、**Playwright**，或通过插件机制接入的第三方渲染器。通过配置中的 `provider` 选择。

**Graphics 后端（绘图后端）**

独立于 HTML 渲染后端的 Python 2D 绘图引擎，内置 **Pillow** 与 **Skia**。既支持调用用户编写的 Python 绘图函数（`DrawingRenderer`），也支持绘制纯数据的 `RasterScene`（`GraphicsRenderer`）。

**Preparation（内容准备）与 `PreparedHtml`**

在真正出图前，先把 Markdown、纯文本或 Jinja2 模板转换成结构化的中立文档 `PreparedHtml`（包含 HTML 字符串、样式表、附带资源与能力需求标记）。这一步不依赖具体渲染引擎。

**资源处理 / 物化（Materialization）**

把 HTML 或模板中引用的本地文件、包资源或远程图片，按安全策略读取并转换成渲染引擎能直接消费的形式（如内存字节、本地路径或 Filehost 临时 URL）。可通过 `ResourceMaterializationPolicy` 控制严格度（`auto` / `strict` / `off`）。

**Capability（引擎专属能力）与租约（Lease）**

某个引擎独有的高级能力，无法抽象到通用 `HtmlRenderer` 中，例如 Playwright 的网页导航与选择器截图、Takumi 的 SVG 与动图编码。通过 `service.capabilities` 获取，并必须使用 `async with ...lease_*()` 按租约借用，离开作用域后自动回收。

**Filehost（内置文件托管服务）**

插件按需启动的独立 aiohttp HTTP 服务，专门用于在远程 Playwright 模式下把机器人本机的大文件或临时资源安全地提供给远端浏览器（带租约 TTL 与认证请求头）。

**`RuntimePlan` 与 `RenderRuntime`**

脱离 Entari 独立使用时的两个底层对象。`build_runtime_plan()` 先根据配置生成一次性的执行计划 `RuntimePlan`（不做 I/O），再调用 `build_runtime()` 构建实际运行并管理生命周期的 `RenderRuntime`。
