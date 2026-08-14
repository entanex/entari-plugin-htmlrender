---
title: 环境变量与配置文件
description: Entari 配置文件中的环境插值边界
---

# 环境变量与配置文件

htmlrender 不读取包含完整配置树的专用环境变量。配置来源由 Entari 管理，`plugins.htmlrender` 下的值直接交给 `HtmlRenderConfig` 校验。

部署秘密可使用 Entari 配置文件支持的环境表达式，而不是把整段 JSON 塞入变量：

```yaml
plugins:
  htmlrender:
    provider: playwright
    provider_config:
      connect_ws:
        endpoint: ${{ env.PLAYWRIGHT_WS_URL }}
```

以下内容不应写入仓库：远程浏览器 token、Sentry DSN、filehost guard value。路径、host allowlist、`public_base_url` 与资源预算应保留为可审查的显式配置。

`HtmlRenderConfig` 不负责加载 `.env`；加载顺序、环境注入与配置重载属于 Entari。
