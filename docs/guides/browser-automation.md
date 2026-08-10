---
title: 操作浏览器页面
description: 通过 runtime 的 Playwright typed capability 租用 Page 与 Browser
---

# 操作浏览器页面

Provider-neutral 渲染不能表达导航、selector 或任意 Playwright 参数；这些操作通过typed capability 暴露：

```python
from entari_plugin_htmlrender import RuntimeSource, resolve_runtime

async def capture(runtime: RuntimeSource, url: str) -> bytes:
    playwright = resolve_runtime(runtime).extensions.playwright
    async with playwright.page(viewport={"width": 1280, "height": 800}) as page:
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        return await page.screenshot(full_page=True, type="png")
```

`Page` 只在 `async with playwright.page()` 内有效；`Browser` 同理。离开上下文、runtime cleanup 或插件热卸载后不得保存或继续使用原生对象。

原生 API 保留 Playwright 自身异常。需要跨 Provider 的 typed artifact 与稳定错误时，使用 `render_html`/`render_markdown` 或 `HtmlRenderer`。导航 URL 必须由调用层建立allowlist；资源策略不提供导航 SSRF 防护。
