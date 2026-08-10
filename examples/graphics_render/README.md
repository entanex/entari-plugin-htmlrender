# Pillow/Skia RasterScene

[`example.py`](example.py) 接收 `RuntimeSource`，从 runtime 的 typed extensions 中选择 Pillow 或 Skia，并渲染同一个 backend-neutral、物理像素级 `RasterScene`。

```yaml
plugins:
  htmlrender:
    provider: null
    graphics:
      backends: [pillow, skia]
      max_pixels: 16777216
      max_concurrency: 2
```

Pillow 与 Skia 不是 HTML Provider，也不读取 `provider_config`。它们共享 runtime拥有的像素与并发预算，但各自通过独立 capability 暴露。
