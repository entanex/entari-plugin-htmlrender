# Takumi capability

[`example.py`](example.py) 直接接收 `TakumiCapability`，再通过`lease_session()` 租用受管理的 `TakumiSession`。租约不能逃逸出异步上下文，也不应保存为进程级单例。

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

本示例只使用 PyPI 0.4.0 已发布接口。上游 `dev` 分支中的 `Document`、`RasterImage` 与 MathJax 预览不属于当前插件能力；Markdown 公式仍应使用 Playwright。
