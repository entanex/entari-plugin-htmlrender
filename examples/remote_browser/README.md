# 远程 Playwright

[`example.py`](example.py) 同时展示 provider-neutral Markdown 渲染与 typed
Playwright capability。`screenshot_url` 接收 `RuntimeSource`，并只在`playwright.page()` 上下文内使用原生 `Page`。

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
      connect_cdp:
        endpoint: http://localhost:9222
```

本目录的 [`docker-compose.yml`](docker-compose.yml) 可启动一个 CDP endpoint。若改用 Playwright WebSocket，只配置 `connect_ws`，不要同时配置两种 endpoint。

示例 URL 必须来自可信调用方。`ResourcePolicy` 约束渲染文档引用的资源，不会替代浏览器导航的 SSRF 防护；生产环境应在调用层建立 scheme/host allowlist，并限制浏览器服务 egress。
