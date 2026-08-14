---
title: 最佳实践
description: 显式 contract、稳定错误、资源边界与 capability 租约
---

# 最佳实践

## 让依赖可见

Entari handler 接收 DI 注入的 `HtmlRenderService`；框架无关的业务函数只接收它真正需要的 `HtmlRenderer`、`TemplateRenderer`、`ResourceAccess` 或`GraphicsRenderer`。不要把 service/runtime 存入模块级对象，也不要建立 locator。

## 优先中立 contract

HTML、文本、Markdown 与模板图片使用 `HtmlRenderer`，模板 HTML 使用`TemplateRenderer`，无 HTML 的像素绘制使用 `GraphicsRenderer`。只有导航、Takumi SVG 或 native access 等无法移植的语义才依赖 typed capability；不要把Provider 专属参数塞进通用 contract。

## 匹配稳定错误

```python
import logging

from entari_plugin_htmlrender import HtmlRenderer
from entari_plugin_htmlrender.errors import ProviderUnavailableError

logger = logging.getLogger(__name__)

async def try_render(renderer: HtmlRenderer) -> bytes | None:
    try:
        return bytes(await renderer.rasterize_html("<p>ready</p>"))
    except ProviderUnavailableError as error:
        logger.warning(
            "Provider %s unavailable (retryable=%s)",
            error.provider_id,
            error.retryable,
        )
        return None
```

不要解析 error message，也不要把底层异常类型作为跨版本契约。进入外部日志前仍需脱敏 HTML、URL、模板变量与 `ErrorCause` snapshot。

## 尊重生命周期

service cleanup 会拒绝新操作并 drain 已获准操作。Playwright Page/Browser、Takumi
session/native renderer 都不能逃逸出 capability lease。热卸载后让 DI 提供新的service，不要复用旧 facade。
