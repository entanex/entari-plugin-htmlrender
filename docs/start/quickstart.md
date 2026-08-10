---
title: 快速开始
description: 在 Entari 中安装、配置并完成第一次渲染
---

# 快速开始

## 安装

```bash
uv add "entari-plugin-htmlrender[playwright]>=0.8.0,<0.9"
uv run playwright install chromium
```

Python 要求为 `>=3.10,<4.0`。core 不携带浏览器或 native backend；也可按需选择`takumi`、`pillow`、`skia`、`filehost`、`sentry`、`prometheus` extra。

## Entari 配置

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    provider_config:
      engine: chromium
```

插件短名是 `htmlrender`。`provider` 等字段直接位于这个映射内，没有额外 wrapper。`probe` 在 Launart preparing 阶段启动并探测 Provider；开发期可用 `warmup`，只做Preparation/模板到 HTML 时可令 `provider: null`。

## 调用

```python
from entari_plugin_htmlrender import RenderedImage, render_markdown
from entari_plugin_htmlrender.host import HtmlRenderService

async def render_help(service: HtmlRenderService) -> RenderedImage:
    return await render_markdown(
        "# Hello, Entari\n\nRendered by htmlrender.",
        width=720,
        runtime=service,
    )
```

让 Entari DI 把 `HtmlRenderService` 传给 handler；上例只展示可复用业务函数，不猜测消息 adapter API。返回的 `RenderedImage` 可通过 `bytes(image)` 交给消息层。

模板和本地资源必须位于 `resources.local_access.allowed_paths` 中。下一步可阅读[渲染内容](../guides/rendering-content.md)、[模板与资源](../guides/templates-and-resources.md)与 [Runtime API](../reference/runtime.md)。
