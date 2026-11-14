# Takumi capability

安装 Takumi 后端，无需安装浏览器：

```bash
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"
```

[`example.py`](example.py) 中的业务函数接收 `TakumiCapability`，再通过 `lease_session()` 租用受管理的 `TakumiSession`。Entari handler 注入 `HtmlRenderService` 后，将 `service.capabilities.takumi` 传给这个函数；插件不直接注入 `TakumiCapability`。租约不能逃逸出异步上下文，也不应保存为进程级单例。

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    provider_config:
      max_concurrency: 4
```

通用 HTML、Markdown 和模板 rasterization 应依赖 `HtmlRenderer`；SVG、动态字体和其他 Takumi 专属语义才进入 capability。若业务入口获得`HtmlRenderService`，传入 `service.capabilities.takumi` 即可。

`example.py` 演示 SVG。需要按来源缓存字体时，可在 `lease_api()` 内调用 `cache_font(font, key)`，再以 `cached_fonts(key)` 检查空间淘汰；`unregister_font()` 与 `clear_fonts()` 用于显式释放。font cache 的字节预算是淘汰依据，不是严格的进程内存峰值上限。

中文等字符需要配置覆盖相应字符的字体，见 [Takumi 字体配置](../../docs/configuration/providers/takumi.md)。默认字体适合先运行本示例的英文内容。

插件当前未接入上游 `Document`、`RasterImage` 与 MathJax API；Markdown 数学公式仍依赖 KaTeX JavaScript，应使用[远程 Playwright](../../docs/configuration/remote-playwright.md)。
