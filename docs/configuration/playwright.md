---
title: Playwright 与远程部署
description: 配置本地或远程 Playwright（WebSocket / CDP）、Docker 部署示例、网络隔离与资源传递策略
icon: lucide/globe
---

# Playwright 与远程部署

当你的业务需要 **JavaScript 执行、复杂浏览器 CSS、外部网页截图、选择器截图或 Markdown 数学公式（KaTeX）** 时，请选择 Playwright 后端。

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.2.0"
```

!!! tip "生产环境强烈推荐使用「远程模式」"
    在机器人宿主机直接运行浏览器会占用大量内存，且容器镜像会变得非常臃肿。将浏览器拆分到独立的 Docker 容器中，机器人只需安装 `[playwright]` Python 客户端并通过 **WebSocket** 连接即可。

## 连接方式对比与配置

=== "远程 WebSocket（生产推荐）"

    通过 Playwright Server 的 WebSocket 端点连接。支持 Chromium / Firefox / WebKit，且会在启动/探测阶段校验客户端与服务端版本。

    ```yaml
    plugins:
      htmlrender:
        provider: playwright
        startup: probe
        provider_config:
          engine: chromium
          connect_ws:
            endpoint: ${{ env.PLAYWRIGHT_WS_URL }} # 例如 ws://playwright:3000/
          remote_local_resource_policy: memory
    ```

    !!! note "版本对齐"
        请确保机器人侧安装的 `playwright` Python 包版本与远程 Playwright Server 的版本完全一致。

=== "远程 CDP（仅 Chromium）"

    连接已开启 Chrome DevTools Protocol 的 Chromium / Chrome 实例。CDP 不执行 Playwright 版本门禁，建议开启 `startup: probe` 验证连通性：

    ```yaml
    plugins:
      htmlrender:
        provider: playwright
        startup: probe
        provider_config:
          engine: chromium
          connect_cdp:
            endpoint: ${{ env.PLAYWRIGHT_CDP_URL }} # 例如 http://chrome:9222
    ```

=== "本地启动（开发调试）"

    不配置 `connect_ws` 与 `connect_cdp` 时，插件会自动启动本地浏览器。首次使用前需安装对应浏览器二进制与系统依赖：

    ```bash
    uv run playwright install --with-deps chromium
    ```

    ```yaml
    plugins:
      htmlrender:
        provider: playwright
        startup: probe
        provider_config:
          engine: chromium
          storage_path: .artifacts/playwright-browsers # 建议按环境隔离浏览器目录
    ```

    - 官方 Firefox / WebKit 不支持 Alpine (musl) 容器。
    - 如果二进制已存在但缺少系统动态库，启动会直接报错，请补装系统依赖。

## 远程 Playwright 服务 Docker 示例

在生产环境中，可以用官方 Playwright 镜像快速起一个独立的浏览器服务（请将镜像标签与你安装的 `playwright` 版本对齐）：

```yaml
services:
  playwright:
    image: mcr.microsoft.com/playwright:v1.60.0-noble
    command: npx -y playwright@1.60.0 run-server --port 3000 --host 0.0.0.0
    ipc: host
    restart: unless-stopped
```

机器人容器中通过 `PLAYWRIGHT_WS_URL=ws://playwright:3000/` 连接即可，无需在机器人镜像里安装任何浏览器或图形库。

---

## `provider_config` 完整参考

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `engine` | `"chromium" \| "firefox" \| "webkit"` | `"chromium"` | 浏览器引擎 |
| `channel` | `str \| None` | `None` | Chromium 发行通道（如 `chrome`、`msedge` 等，仅 `engine: chromium` 有效） |
| `executable_path` | `Path \| None` | `None` | 手动指定本地浏览器可执行文件路径 |
| `launch_args` | `str \| None` | `None` | 本地启动附加参数 |
| `proxy_server` / `proxy_bypass` | `str \| None` | `None` | 浏览器代理地址与绕过列表 |
| `connect_ws.endpoint` | `str \| None` | `None` | 远程 WebSocket 端点（与 `connect_cdp` 互斥） |
| `connect_cdp.endpoint` | `str \| None` | `None` | 远程 CDP 端点（仅 Chromium，与 `connect_ws` 互斥） |
| `storage_path` | `Path \| None` | `None` | 本地浏览器下载/存放目录（默认使用插件数据目录） |
| `install_mirror` / `install_proxy` | `str \| None` | `None` | 浏览器下载镜像或代理 |
| `skip_browser_install` | `bool` | `false` | 跳过自动安装检查 |
| `close_on_exit` | `bool` | `true` | 插件关闭时是否关闭浏览器连接/进程 |
| `materialization_policy` | `"off" \| "auto" \| "strict"` | `"auto"` | 默认资源处理策略 |
| `remote_local_resource_policy` | `"memory" \| "passthrough" \| "filehost" \| "error"` | `"memory"` | 远程模式下本地资源的传递方式 |
| `local_local_resource_policy` | `"file" \| "passthrough" \| "filehost"` | `"file"` | 本地模式下本地资源的传递方式 |

## 资源传递策略 { #resource-delivery }

当模板引用了机器人本机的图片或静态文件时，浏览器如何读取这些文件取决于上述两个策略字段：

- **`memory`（远程模式默认）**：机器人读取本地白名单文件后，在路由拦截中直接把字节返回给远程浏览器。**无需额外开放 HTTP 端口**，配置最简单。
- **`filehost`**：通过插件内置的独立 HTTP 服务（Filehost）提供大文件或复用资源，需安装 `[filehost]` 并配置 `resources.filehost.public_base_url`，详见 [Filehost 配置](resources-and-security.md#filehost)。
- **`file`（本地模式默认）**：直接让本地浏览器读取白名单内的本地文件路径。
- **`passthrough`**：原样透传引用，不做额外托管。
- **`error`**（仅远程模式）：遇到本地资源引用时直接拒绝报错。

## 托管渲染的网络隔离机制

当你通过 `HtmlRenderer`（如 `rasterize_html`、`rasterize_markdown`、`rasterize_template`）调用 Playwright 时，插件会自动开启网络守卫：

1. **受控代拉**：页面里的所有外部资源只允许 HTTP(S) `GET` 请求，且由机器人侧的受控网络客户端代为下载（浏览器本身不直连外部地址）。非 `GET` 请求、WebSocket 和 Service Worker 均被拦截。
2. **逐跳校验重定向**：每次 HTTP 重定向都会重新核对 `resources.remote_access` 的域名黑/白名单与解析后的 IP/CIDR；禁止静态资源重定向到 `text/html`。
3. **不泄露凭据**：不会自动转发浏览器 Cookie，Filehost 认证头也严格绑定单个精确 URL，绝不跨重定向转发。

!!! warning "边界说明"
    该守卫仅保护托管渲染中的 HTTP(S) 资源拉取，不等同于完整的 Chromium 沙箱隔离。此外，通过 `service.capabilities.playwright.lease_page()` 进行的原生浏览器操作不受此守卫约束，需由业务自行校验 URL。
