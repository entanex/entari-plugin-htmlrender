# 本地模板渲染

[`example.py`](example.py) 展示 Entari handler 获得 DI 注入的`HtmlRenderService` 后，如何通过 `service.renderer` rasterize `TemplateRef` 与文本。模块只返回`RenderedImage`，不绑定任何消息 adapter。

静态模板推荐使用 Takumi，无需安装浏览器：

```bash
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"
```

在 Entari 配置中选择 Takumi，并允许模板目录：

```yaml
plugins:
  htmlrender:
    provider: takumi
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

模板变量由调用方传入；把返回 artifact 转交消息层时再显式调用 `bytes(image)`。中文用户名、签名或统计标签需要按 [Takumi 字体配置](../../docs/configuration/providers/takumi.md)提供字体，系统字体名称不会自动授权或加载字体文件。

`profile.html` 用 `<style>{% include "style.css" %}</style>` 在 Jinja2 渲染时内联样式，避免 Takumi 不支持的 `<link rel="stylesheet">`。HTML/CSS 支持范围与浏览器不同，修改模板样式后应检查排版结果。依赖 JavaScript 或浏览器布局的模板请使用[远程 Playwright](../../docs/configuration/remote-playwright.md)。
