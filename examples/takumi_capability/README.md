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
