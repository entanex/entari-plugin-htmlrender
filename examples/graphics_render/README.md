# Pillow/Skia RasterScene

[`example.py`](example.py) 只接收 `GraphicsRenderer`，并渲染一个与实现无关、物理像素级的 `RasterScene`。Pillow 或 Skia 由 composition 配置选择，业务函数不按实现分支。

```yaml
plugins:
  htmlrender:
    provider: null
    graphics:
      backend: pillow
      max_pixels: 16777216
      max_concurrency: 2
```

Pillow 与 Skia 不是 HTML Provider，也不读取 `provider_config`。它们实现同一个`GraphicsRenderer`；Entari handler 可传入 `service.graphics`。
