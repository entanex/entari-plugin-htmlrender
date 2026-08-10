---
title: 最佳实践
description: 显式 runtime、稳定错误、资源边界与 capability 租约
---

# 最佳实践

## 让依赖可见

业务函数接收 `RuntimeSource`，Entari handler 接收 DI 注入的`HtmlRenderService`，每次调用显式传 `runtime=`。只在一个任务内有多次调用时使用`runtime_context(service)`；不要建立模块级 runtime locator。

## 优先通用 API

HTML、文本、Markdown 与模板优先使用 caller-first 顶层函数。只有导航、node、SVG、animation 或指定 Graphics backend 等无法移植的语义才进入 typed
capability。不要把 Provider 专属参数塞进通用 request。

## 匹配稳定错误

```python
import logging

from entari_plugin_htmlrender import ProviderUnavailable, RuntimeSource, render_html

logger = logging.getLogger(__name__)

async def try_render(runtime: RuntimeSource) -> bytes | None:
    try:
        return bytes(await render_html("<p>ready</p>", runtime=runtime))
    except ProviderUnavailable as error:
        logger.warning("Render provider unavailable: %s", error)
        return None
```

不要解析 error message，也不要把底层异常类型作为跨版本契约。进入外部日志前仍需脱敏 HTML、URL、模板变量与 cause snapshot。

## 尊重生命周期

service cleanup 会拒绝新操作并 drain 已获准操作。Playwright Page/Browser、Takumi
API/native renderer 都不能逃逸出 capability 上下文。热卸载后让 DI 提供新的 service，不要复用旧 runtime 或 facade。
