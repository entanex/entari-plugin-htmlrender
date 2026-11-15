---
title: 远程 Playwright
description: 通过 CDP 或 Playwright WebSocket 使用独立浏览器服务
icon: lucide/cloud-cog
---

# 远程 Playwright

不需要 JavaScript、导航或浏览器页面能力时，优先使用 [Takumi](providers/takumi.md)。需要这些能力时，远程 Playwright 是目标部署形态：浏览器二进制、系统图形库与进程生命周期位于独立服务。客户端与服务端 Playwright 版本应匹配；CDP 只支持 Chromium，Playwright WebSocket 可支持更多引擎。

## 依赖与计划弃用

远程连接仍要求 Bot 环境安装 Playwright Python client：

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.2.0"
```

配置 `connect_ws` 或 `connect_cdp` 后，Bot 环境不需要执行 `playwright install`，也不需要安装浏览器二进制及其系统依赖；远程服务必须提供匹配的浏览器。本插件的 Playwright 后端在不久的将来将仅保留这两种远程连接。当前版本仍支持 Bot 本地浏览器安装、管理与启动，但该路径计划弃用，具体移除版本和时间尚未确定；现有本地细节见 [Playwright 配置](providers/playwright.md#browser-runtime-requirements)。

## CDP

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
      connect_cdp:
        endpoint: http://browser:9222
```

## WebSocket

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
      connect_ws:
        endpoint: ws://browser:3000/
```

两种 endpoint 互斥。凭据用 Entari 环境插值注入，不提交到仓库。

### WS 版本门禁与启动探测 { #ws-version-gate-and-startup-probe }

WebSocket 连接在 startup/probe 阶段比较客户端与远端版本。版本门禁 fail-open：远端无法报告版本时会记录诊断并继续，但软门禁不能证明任意版本组合兼容。发现明确不兼容时应在 preparing 阶段失败，而不是把问题推迟到首个业务请求。

CDP 模式不执行 Playwright client/server 版本门禁；它只使用 Chromium DevTools Protocol，仍需通过真实 probe 验证目标服务能力。

远程浏览器无法直接读取宿主本地路径。优先使用内存/data URL；资源较大或浏览器与宿主分离时配置显式 filehost。选择 filehost transport 时必须提供 Bot 可连接的 `resources.filehost.public_base_url`；`filehost` extra 只用于安装 `py-machineid` 以改善默认请求头值的机器标识派生。未安装该 extra 或机器标识读取失败时，publisher 会回退到 MAC 地址派生标识；显式配置 `resources.filehost.request_header_value` 时直接使用该值。受管理的 HTML rendering 由 Bot 获取 filehost URL 后把响应交给浏览器，因此私网目标还须匹配 `allow_private_networks`。

`startup: probe` 在 Launart preparing 阶段建立连接并执行最小探测。业务 handler不应再次手工 startup；需要原生页面时通过`service.capabilities.playwright.lease_page()` 建立显式租约。

受管理的 HTML rasterization 只把 HTTP(S) `GET` 请求交给 Bot-side 的 pinned resource transport；浏览器不直接连接这些地址，WebSocket 与非 `GET` 请求会被拒绝，service worker 会被阻止。每跳地址都须符合 `resources.remote_access`：非公网地址必须列入 `allow_private_networks`，旧布尔值无效，`deny_hosts` 优先。发布授权头只适用于原发布 URL，redirect 到不同 URL 时不会沿用，且不会进入授权缓存。该机制保护 HTTP(S) 资源访问，不构成完整 Chromium sandbox；`lease_page()` / `lease_browser()` 的原生导航及后续请求仍由调用方负责策略校验。
