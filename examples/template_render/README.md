# 本地模板渲染

[`example.py`](example.py) 展示 Entari handler 获得 DI 注入的`HtmlRenderService` 后，如何调用 `render_template` 与 `render_text` 并显式传入`runtime=service`。模块只返回 `RenderedImage`，不绑定任何消息 adapter。

安装 Playwright 或 Takumi extra，并在 Entari 配置中允许模板目录：

```yaml
plugins:
  htmlrender:
    provider: playwright
    startup: probe
    resources:
      local_access:
        allowed_paths:
          - examples/template_render/templates
```

```text
template_render/
├── example.py
└── templates/
    ├── profile.html
    └── style.css
```

模板变量由调用方传入；把返回 artifact 转交消息层时再显式调用 `bytes(image)`。
