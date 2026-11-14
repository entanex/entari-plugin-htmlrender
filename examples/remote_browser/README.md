# 远程 Playwright

不需要 JavaScript、导航或浏览器页面能力时，优先使用 Takumi。下面的示例面向需要浏览器语义的远程 Playwright 部署。

[`example.py`](example.py) 同时展示 provider-neutral Markdown rasterization 与 typed Playwright capability。两个函数分别接收 `HtmlRenderer` 与 `PlaywrightCapability`；原生 `Page` 只在 `lease_page()` 上下文内使用。

Bot 环境仍需 `entari-plugin-htmlrender[playwright]` extra，但配置远程 endpoint 后无需执行 `playwright install`，也无需安装浏览器二进制及系统依赖。本目录的 Compose 服务负责浏览器；实际部署必须使用与客户端兼容的版本。

本插件的 Playwright 后端将在不久的将来弃用本地浏览器安装、管理与启动，仅保留 `connect_ws` 与 `connect_cdp` 远程连接。当前版本仍支持本地模式，具体移除版本和时间尚未确定。

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

示例 URL 必须来自可信调用方。`ResourceMaterializationPolicy` 只约束文档资源物化，不会替代浏览器导航的 SSRF 防护；生产环境应在调用层建立 scheme/host allowlist，并限制浏览器服务 egress。
