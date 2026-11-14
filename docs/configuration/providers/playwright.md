---
title: Playwright 配置
description: 本地/远程浏览器连接、资源 transport 与 typed Capability
icon: lucide/monitor-cog
---

# Playwright 配置

## 安装与最小配置

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.2.0,<0.3"
```

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
      connect_ws:
        endpoint: ws://playwright:3000/
      remote_local_resource_policy: memory
```

## 部署优先级 { #deployment-priority }

1. **首选：Docker 远程 Playwright。** 在独立容器中部署版本匹配的 Playwright browser service，Bot 通过 `connect_ws.endpoint` 连接。浏览器二进制、Linux 系统依赖、sandbox 与进程生命周期都留在服务容器内；Bot 宿主机只需要 `playwright` extra。生产环境默认采用这一形态，具体拓扑见[远程 Playwright 部署](../remote-playwright.md)。
2. **第二选项：Bot 宿主机本地 Playwright。** 不配置 `connect_ws` / `connect_cdp`，由 Bot 直接启动浏览器。它适合本地开发、单机部署或无法增加独立服务的环境，但宿主机必须承担浏览器下载、系统动态库、权限和进程清理。

CDP 用于接入已有 Chromium，不是一般部署的首选替代；它不支持 Firefox 或 WebKit，协议能力也不同于版本匹配的 Playwright WS 服务。

## 浏览器运行环境 { #browser-runtime-requirements }

`playwright` extra 只安装 Playwright Python client。每个 Playwright 版本都要求特定版本的浏览器二进制；升级依赖或更新 lockfile 后，需要用同一个 Python 环境重新执行浏览器安装。上游的[浏览器安装说明](https://playwright.dev/python/docs/browsers/)也把 Python package、浏览器二进制和 Linux 系统依赖视为三个独立层次。

采用第二选项时，在 macOS 或 Windows 安装选中的浏览器：

```bash
uv run playwright install chromium
```

Debian/Ubuntu、容器与 CI 应在镜像构建阶段同时安装浏览器及其系统依赖：

```bash
uv run playwright install --with-deps chromium
```

!!! warning "单机模式必须保持 client 与 browser revision 强一致"

    `storage_path` 中的浏览器必须由当前项目虚拟环境内解析出的同一 Playwright Python package 版本安装。这里的“强一致”是指 client 声明的 browser revision 完全匹配，并非只比较 Chromium 显示的产品版本字符串。

    不要手工替换目录内的浏览器 executable，也不要让全局 Playwright CLI 或其他虚拟环境对同一个 `storage_path` / `PLAYWRIGHT_BROWSERS_PATH` 执行安装、升级、卸载或缓存清理。这些操作可能移除当前 client 要求的 revision，使单机 Provider 立即不可用。

    为每个项目虚拟环境分配独占目录，并始终通过该项目的 `uv run` 安装：

    ```bash
    PLAYWRIGHT_BROWSERS_PATH=/var/lib/htmlrender/playwright-project \
      uv run playwright install --with-deps chromium
    ```

    ```yaml
    plugins:
      htmlrender:
        provider: playwright
        startup: probe
        provider_config:
          storage_path: /var/lib/htmlrender/playwright-project
          skip_browser_install: true
    ```

    安装用户必须能写入该目录，Bot 服务用户必须能读取并执行其中的文件。依赖更新后，即使目录仍然存在，也要从更新后的同一虚拟环境重新执行安装。

将 `chromium` 替换为实际配置的 `engine`。`--with-deps` 在 Linux 上会调用系统包管理器，构建用户必须有相应权限；生产服务进程不应依赖启动时临时取得 root 或访问下载源。htmlrender 在本地浏览器二进制确实缺失时会尝试一次同样的安装和重启，但已经存在浏览器而系统动态库不完整时会直接报告 runtime dependency failure。生产部署应预装完整环境；确认 `storage_path` 中已有匹配版本后，可以设置 `skip_browser_install: true` 禁止运行时下载。

使用 Playwright 官方容器镜像时，镜像已经包含浏览器与系统依赖，但不包含项目的 Python package；镜像 tag 必须与 lockfile 最终解析到的 Playwright 版本匹配。官方浏览器不支持 Alpine/musl 上的 Firefox 与 WebKit，容器部署应使用受支持的 glibc 基础镜像。详见上游的 [Docker 说明](https://playwright.dev/python/docs/docker/)。

推荐的 Docker/WS 远程模式下，Bot 进程仍需 `playwright` extra，但不需要本地浏览器二进制及其系统依赖；这些要求由远程服务承担。WS 服务与 client 必须精确锁定到同一 Playwright 版本。连接前虽有版本风险门禁，但它在相邻 minor、部分 patch 差异或无法探测远端版本时仍会继续，不能代替版本锁定；CDP 则完全不执行该版本比较。详细行为与服务端检查表见[远程 Playwright 部署](../remote-playwright.md#ws-version-gate-and-startup-probe)。

下表所有字段均位于 `provider_config`：

| 完整路径 | 默认值 | 说明 |
| --- | --- | --- |
| `provider_config.engine` | `chromium` | `chromium`、`firefox`、`webkit` |
| `provider_config.channel` | `null` | Chromium channel |
| `provider_config.executable_path` | `null` | 自定义浏览器路径 |
| `provider_config.launch_args` | `null` | 本地 launch 参数字符串 |
| `provider_config.proxy_server` | `null` | 浏览器代理 |
| `provider_config.proxy_bypass` | `null` | 代理绕过规则 |
| `provider_config.connect_ws.endpoint` | `null` | Playwright WebSocket endpoint |
| `provider_config.connect_cdp.endpoint` | `null` | Chromium CDP endpoint |
| `provider_config.install_mirror` | `null` | 浏览器安装镜像 |
| `provider_config.install_proxy` | `null` | 浏览器安装代理 |
| `provider_config.skip_browser_install` | `false` | 缺少本地浏览器时禁止自动安装 |
| `provider_config.close_on_exit` | `true` | composition 关闭时关闭本地浏览器 |
| `provider_config.storage_path` | `null` | Playwright 浏览器存储目录；默认使用插件数据目录 |

`channel` 只适用于 Chromium；CDP 只适用于 Chromium；WS 与 CDP endpoint互斥。空的 `executable_path` 会归一化为 `null`。

`storage_path` 仅覆盖 Playwright 浏览器文件与运行时快照的存储位置。单机部署不得让不同项目虚拟环境共享该目录；对应的安装命令必须通过同一路径的 `PLAYWRIGHT_BROWSERS_PATH` 定位它。

## 资源 transport

| 完整路径 | 默认值 | 说明 |
| --- | --- | --- |
| `provider_config.materialization_policy` | `auto` | `off`、`auto`、`strict` |
| `provider_config.remote_local_resource_policy` | `memory` | `memory`、`passthrough`、`filehost`、`error` |
| `provider_config.local_local_resource_policy` | `file` | `file`、`passthrough`、`filehost` |

未传每次调用的 `materialization_policy` 时，执行端采用 Provider 的`materialization_policy`；显式 `ResourceMaterializationPolicy` 会覆盖该默认值。`off` 不读取、物化或发布文档引用；若 transport 是 `filehost`，composition 仍会准备 publisher，使后续单次调用可以覆盖为 `auto` 或 `strict`。`auto` 容忍无法读取的引用，`strict` 将其报告为资源错误。

远程模式推荐 `memory`：本地图片、字体和 CSS 被物化为 render-scoped asset，由页面 route 返回，不要求共享 filesystem。`passthrough` 仅适用于显式共享卷；`error` 用于禁止所有本地引用。

受管理的 HTML rasterization 只允许 HTTP(S) `GET` 请求，并由 Bot 的 pinned transport 获取；浏览器不直接连接这些地址。redirect 在 Bot 内继续受同一主机名、DNS/IP 与最终连接地址校验，之后把最终响应交给浏览器。非 `GET` 请求与 WebSocket 会被拒绝，service worker 会被阻止。此保护仅限 HTTP(S) 资源访问，不等同于完整的 Chromium sandbox。

受管 GET 不会复制浏览器生成的 cookie 或请求头。显式 `PageConfig.user_agent` 会作为 `User-Agent` 基础值，`extra_http_headers` 不区分大小写覆盖同名预设；精确 `PublishedResource` 授权头再做最终覆盖。未显式配置头部时不额外注入。redirect 到不同 URL 时不会转发这些请求头，而是重新经过资源策略校验。

`allow_hosts: []` 不限制主机名但仍执行 IP 检查；非空列表只允许列出的主机及子域。访问回环、RFC 1918、链路本地、CGNAT/shared `100.64.0.0/10`、ULA 等非公网地址时，还要在 `allow_private_networks` 中列出对应 IP/CIDR。布尔值已失效，默认值为 `[]`；`deny_hosts` 始终优先。

`filehost` 是需要真实 HTTP URL 时的兼容 transport，由 htmlrender 内置的 hosted asset store 提供。可选 `filehost` extra 会安装 `py-machineid`，用于派生默认请求头守卫值：

```bash
uv add "entari-plugin-htmlrender[playwright,filehost]>=0.2.0,<0.3"
```

不安装该 extra 时 transport 仍可使用内置机器标识回退；对多副本或需要显式轮换的部署，直接配置 secret `resources.filehost.request_header_value`，不要依赖自动派生值。

`memory` 使用 render-scoped Page route 返回内存资源。`filehost` 的授权请求头由 Bot 添加到 `PublishedResource` 的精确 URL；redirect 到不同 URL 时不会转发该请求头，也不会缓存为该 URL 以外的授权。若 `public_base_url` 解析到非公网地址，它还必须匹配 `allow_private_networks`，且 Bot 必须能连接该 URL。

redirect 跟随和响应供给并不等价于浏览器直接访问。重定向 CSS 会按 `ResourceContent.final_url` 解析其相对引用；重定向后的 `text/html` 或 `application/xhtml+xml` 响应目前因无法安全保留 document base 而被拒绝。JavaScript、模块与 XML 的相对 URL 语义不做转换。

!!! warning "filehost 代理必须转交 Bot 的授权请求头"

    受管理请求中的 `resources.filehost.request_header_name` 由 Bot 发出。反向代理必须把该请求头传给 filehost server；浏览器的预设请求头不能替代这项 URL-scoped 授权。

filehost 运行参数由核心 Resource Service 管理，位于 `resources.filehost`：

| 完整路径 | 默认值 |
| --- | --- |
| `resources.filehost.cache_ttl_seconds` | `300.0` |
| `resources.filehost.prewarm_enabled` | `true` |
| `resources.filehost.prewarm_paths` | `[]` |
| `resources.filehost.prewarm_max_files` | `256` |
| `resources.filehost.prewarm_extensions` | `[]` |
| `resources.filehost.request_header_name` | `X-HTMLRender-Filehost-Request` |
| `resources.filehost.request_header_value` | `null` |
| `resources.filehost.request_header_salt` | 内置稳定值 |

路径授权不在 Provider 配置中；统一使用`resources.local_access.allow_any_path` 与`resources.local_access.allowed_paths`。

## Markdown 数学与 JavaScript

Markdown 中的 `pymdownx.arithmatex(generic=True, smart_dollar=True)` 标记需要浏览器端 KaTeX 初始化脚本才能显示为排版公式。`$x$` 与 `\(x\)` 是行内公式，`$ x $` 保持原文；`$$...$$`、`\[...\]` 与独立的 `\begin{env}...\end{env}` 需要独占段落或进入块解析。Playwright 会执行页面 JavaScript，因此可以完成这层客户端排版；`rasterize_markdown()` 与先 `prepare_markdown()` 再 `rasterize_prepared()` 都沿用同一 Provider 执行边界。

初始化脚本只处理 `.arithmatex[data-htmlrender-arithmatex]`，不对整个页面执行 dollar/slash auto-render。没有内部标记的原始 HTML `.arithmatex` 容器不会被脚本处理；代码 span 与 fenced code 中的 `$`、`\(` 或 `\[` 保持字面量。如果页面策略、资源物化或自定义 HTML 移除了公式脚本及样式，浏览器中可能仍显示 TeX 标记。排查公式输出时应同时检查脚本是否执行完成、所需 CSS 是否可用，以及内容是否在完成排版前已被截图。

## typed Capability

`HtmlRenderer` 不接受导航、header 或 User-Agent。页面控制通过显式 capability lease：

```python
from entari_plugin_htmlrender.capabilities import PlaywrightCapability

async def open_page(playwright: PlaywrightCapability) -> None:
    async with playwright.lease_page(
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"X-Trace": "example"},
    ) as page:
        await page.goto("https://example.com")
```

远程部署与安全边界见 [远程 Playwright](../remote-playwright.md)。

若需要完整 `Browser` 能力而不只是一张自动回收的 Page，可改用`playwright.lease_browser()`。原生对象同样不能逃逸租约；生命周期、资源所有权和telemetry 约束见 [Capability 参考](../../reference/capabilities.md#playwright)。

`lease_page()` 与 `lease_browser()` 返回由调用方持有的原生 Playwright 对象。调用方在该租约内执行的导航和后续 HTTP(S) 请求不受受管理 rasterization 请求链路的自动保护，仍须自行执行 scheme、host、DNS/IP 与 redirect 校验。
