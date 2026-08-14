---
title: 操作浏览器页面
description: 通过 PlaywrightCapability 租用 Page 与 Browser
---

# 操作浏览器页面

中立 HTML rasterization 不表达导航、selector 或任意 Playwright 参数；这些操作由typed capability 暴露：

```python
from entari_plugin_htmlrender.capabilities import PlaywrightCapability

async def capture(playwright: PlaywrightCapability, url: str) -> bytes:
    async with playwright.lease_page(viewport={"width": 1280, "height": 800}) as page:
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        return await page.screenshot(full_page=True, type="png")
```

Entari handler 可把 `service.capabilities.playwright` 传给该函数。`Page` 只在`lease_page()` 上下文内有效；`Browser` 同理使用 `lease_browser()`。离开上下文、runtime cleanup 或插件热卸载后不得保存或继续使用原生对象。

原生 API 保留 Playwright 自身异常。需要跨 Provider 的 typed artifact 与稳定错误时，依赖 `HtmlRenderer`。导航 URL 必须由调用层建立 allowlist；资源 materialization
policy 不提供导航 SSRF 防护。
