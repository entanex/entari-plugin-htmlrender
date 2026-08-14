# Echo Provider

这是一个最小第三方 Provider distribution：它不依赖浏览器或 native renderer，每次 rasterize 操作都返回配置颜色的 1×1 PNG。

```bash
uv add --editable ./examples/echo-provider
```

```yaml
plugins:
  htmlrender:
    provider: echo
    startup: probe
    provider_config:
      color: "#663399"
```

distribution 通过 `entari_plugin_htmlrender.providers.v2` entry-point group 注册`PROVIDER`。实现展示 typed config、无副作用 availability、lifecycle/executor
binding 与 composition 注入的 `ProviderDependencies.resources` 边界。
