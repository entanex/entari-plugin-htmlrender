# Takumi capability

[`example.py`](example.py) 从显式 `RuntimeSource` 解析 runtime，再通过`runtime.extensions.takumi.api()` 租用受管理的 Takumi API。租约不能逃逸出异步上下文，也不应保存为进程级单例。

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    provider_config:
      max_concurrency: 4
```

通用 HTML、Markdown 和模板渲染优先使用顶层 API；node、measure、SVG、animation和动态字体等专属语义才进入 Takumi capability。
