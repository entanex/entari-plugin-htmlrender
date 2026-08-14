---
title: 远程 Playwright
description: 通过 CDP 或 Playwright WebSocket 使用独立浏览器服务
---

# 远程 Playwright

生产环境可把浏览器二进制、系统图形库与进程生命周期放进独立容器。客户端与服务端Playwright 版本应匹配；CDP 只支持 Chromium，Playwright WebSocket 可支持更多引擎。

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

CDP 模式不执行 Playwright client/server 版本门禁；它只使用 Chromium DevTools
Protocol，仍需通过真实 probe 验证目标服务能力。

远程浏览器无法直接读取宿主本地路径。优先使用内存/data URL；资源较大或浏览器与宿主分离时配置显式 filehost。若选中 filehost strategy，必须安装 `filehost` extra并提供外部可达的 `resources.filehost.public_base_url`。

`startup: probe` 在 Launart preparing 阶段建立连接并执行最小探测。业务 handler不应再次手工 startup；需要原生页面时通过`service.capabilities.playwright.lease_page()` 建立显式租约。
