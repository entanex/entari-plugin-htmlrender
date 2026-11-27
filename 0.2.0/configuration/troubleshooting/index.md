# 故障排查与常见问题

遇到问题时，先对照下方的异常速查表，再展开对应的详细排查步骤。

## 常见异常速查

| 异常类型 | 典型原因 | 优先排查方向 |
| --- | --- | --- |
| `RuntimeUnavailableError` | 缓存了旧的 service/renderer，或插件启动/清理失败 | 改为通过 DI 获取最新实例；检查启动日志并重载插件 |
| `ProviderNotFoundError` | `provider` 拼写错误或未安装对应 extra | 检查 `provider` 值与是否安装了 `[takumi]` / `[playwright]` |
| `ProviderUnavailableError` | 浏览器缺失、远程地址不通或版本不匹配 | 查看异常的 `provider_id`、`reason`、`retryable` 字段 |
| `UnsupportedDocumentFeatureError` | 把含数学公式/JS 的文档交给了 Takumi | 改用 Playwright，或预渲染公式为静态 SVG |
| `CapabilityUnavailableError` | 访问了未启用的引擎专属能力 | 用 `capabilities.available_names` 先做判断 |
| `GraphicsBackendUnavailableError` | 缺少 Pillow/Skia 依赖或 Skia 系统共享库 | 运行 `python3 -c "import skia"` 检查系统库 |
| `ResourceAccessDeniedError` | 本地文件不在白名单，或远程命中内网/黑名单 | 检查 `allowed_paths`、`allow_hosts` 与 `allow_private_networks` |
| `RenderOutputLimitError` | 输出像素、自动高度或文件体积超预算 | 调大 `html.*` / `graphics.*` 预算或缩小视口/分页 |

---

## 按现象排查

> [!NOTE]
>
> **Takumi 渲染中文全是方块或乱码**
>
> Takumi 默认内置字体不包含完整中文字形。请同时检查三件事：
>
> 1. 字体文件所在目录已加入 `resources.local_access.allowed_paths`。
> 2. 在 `provider_config.fonts` 中注册了该字体文件。
> 3. 在 `provider_config.font_families` 或 CSS `font-family` 中使用了注册的字体名称。
>
> 详见 [Takumi 字体配置](<https://entanex.github.io/entari-plugin-htmlrender/0.2.0/configuration/takumi/index.md#fonts>)。

> [!NOTE]
>
> **Takumi 渲染模板时外部 CSS 或网络图片不生效**
>
> - Takumi 不支持 `<link rel="stylesheet">`、`@import` 和 `@font-face`，请改用 `<style>{% include "style.css" %}</style>` 内联样式。
> - Takumi 不会在排版时自动下载网络图片，请先通过 `ResourceAccess.fetch_bytes()` 拉取字节后再传入模板。

> [!NOTE]
>
> **Markdown 数学公式没有被渲染，或者直接报错**
>
> 1. 检查语法：行内公式 `$x$` 两端\*\*不能有空格\*\*（`$ x $` 会被当作普通文本）；块级 `$$...$$` 必须\*\*独占段落\*\*。
> 2. 检查引擎：数学公式依赖 KaTeX JavaScript，只有 **Playwright** 支持。交给 Takumi 会直接抛出 `UnsupportedDocumentFeatureError`。

> [!NOTE]
>
> **插件热重载后报错 `RuntimeUnavailableError`**
>
> 通常是因为业务代码把 `HtmlRenderService`、`HtmlRenderer`、`HtmlPreparer` 或 `capabilities` 存进了模块级全局变量。插件重载后旧的运行时已经关闭，继续调用就会报错。
>
> **解决方式**：每次在事件处理函数里通过 Entari 依赖注入获取，不要在模块顶层缓存任何服务对象。

> [!NOTE]
>
> **关闭或重载插件时卡住很久**
>
> `cleanup` 阶段会等待所有借出的租约归还。如果你在代码中调用了 `lease_page()`、`lease_browser()`、`lease_session()`、`lease_api()`、`lease_native_renderer()` 或 `resources.publish()`，请检查是否有对象逃逸出了 `async with` 作用域或存在未取消的协程一直持有租约。

> [!NOTE]
>
> **Linux 上安装 `[skia]` 后无法导入或报缺 `.so`**
>
> `skia-python` 依赖宿主机安装以下系统共享库，且不支持 Alpine (musl)：
>
> ```bash
> # Debian / Ubuntu 示例
> apt-get update && apt-get install -y libegl1 libgl1 libexpat1 libstdc++6 zlib1g
> ```
>
> 安装后运行 `uv run python3 -c "import skia"` 验证。

> [!NOTE]
>
> **远程 Playwright 提示版本不兼容或连接失败**
>
> 1. 确认远程 Playwright Server 与机器人侧 `playwright` Python 包的版本完全一致。
> 2. 确认网络可达，且配置的是 `connect_ws.endpoint`（或 Chromium 专用的 `connect_cdp.endpoint`），两者不能同时填写。
> 3. 如果使用 Filehost 传递本地资源，确保配置了绝对地址 `resources.filehost.public_base_url`，且反代透传了 `X-HTMLRender-Filehost-Request` 请求头。

> [!NOTE]
>
> **只用 Python 绘图或模板转 HTML，需要装 Takumi 或 Playwright 吗？**
>
> 不需要。保持 `provider: null` 和 `startup: off`，只安装你实际用到的依赖（如 `[pillow]`）即可。
