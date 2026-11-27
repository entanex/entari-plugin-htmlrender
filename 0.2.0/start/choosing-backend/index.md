# 如何选择渲染方案

`entari-plugin-htmlrender` 把 **HTML 网页渲染** 和 **Python 绘图** 分成了两条独立的能力线：

- **HTML 渲染后端（`provider`）**：负责把 HTML、Markdown、纯文本、Jinja2 模板转成图片，可选 **Takumi** 或 **Playwright**（或第三方扩展）。
- **Python 绘图后端（`graphics`）**：负责用 Python 代码或声明式场景直接绘图，可选 **Pillow** 或 **Skia**，可与任意 HTML 后端同时启用，也可单独使用。

## 选型决策图

```
flowchart TD
    A["你需要把什么画成图片？"] --> B{"使用 HTML / Markdown / 模板？"}
    B -- "是" --> C{"需要 JS、网页截图、数学公式\n或完整浏览器 CSS 特性？"}
    C -- "不需要（静态内容为主）" --> T["选择 Takumi\n无需浏览器 · 轻量快速"]
    C -- "需要" --> P["选择 Playwright\n推荐连接远程浏览器服务"]
    B -- "否（纯 Python 代码绘图）" --> D{"追求高性能矢量/抗锯齿效果\n且环境满足系统库要求？"}
    D -- "否（追求零额外系统依赖）" --> PIL["选择 Pillow\n开箱即用 · 跨平台省心"]
    D -- "是" --> SK["选择 Skia\n高性能 2D 矢量引擎"]
```

## 详细对比

| 方案 | 擅长场景 | 主要限制与代价 | 所需可选依赖 |
| --- | --- | --- | --- |
| **Takumi** | 静态卡片、帮助菜单、排行榜、Markdown 文档、Jinja2 模板、SVG、布局测量、动图 | 不执行 JavaScript；不支持 Markdown 数学公式；CSS 特性比浏览器精简；中文需手动配置字体 | `[takumi]` |
| **Playwright** | 复杂浏览器布局、动态图表（如 ECharts）、外部网页截图、选择器截图、Markdown 数学公式（KaTeX） | 需要运行真实浏览器（生产环境推荐独立部署远程浏览器服务） | `[playwright]` |
| **Pillow** | 用 Python 代码绘制常规拼图、头像合成、图表、像素级控制 | 不解析 HTML / Markdown | `[pillow]` |
| **Skia** | 用 Python 代码绘制高质量矢量图形、渐变、圆角、复杂路径 | 不解析 HTML / Markdown；仅提供预编译 wheel，Linux 需特定系统图形库且不支持 Alpine/musl | `[skia]` |

## 常见疑问

> [!NOTE]
>
> **已有浏览器模板，能直接切到 Takumi 吗？**
>
> 可以尝试，但需要注意三点差异：
>
> 1. **样式必须内联**：Takumi 不支持 `<link rel="stylesheet">`、`@import` 和 `@font-face`，请改用 `<style>` 内联（在 Jinja2 中可直接写 `<style>{% include "style.css" %}</style>`）。
> 2. **中文字体需显式配置**：将字体文件加入本地白名单并在 `provider_config.fonts` 中注册。
> 3. **排查浏览器专属 CSS 和脚本**：如果模板依赖 JavaScript 或较新的浏览器布局特性，仍应使用 Playwright。

> [!NOTE]
>
> **可以同时使用 HTML 渲染和 Python 绘图吗？**
>
> 完全可以，而且非常常见。例如用 Takumi 渲染常规 Markdown/模板卡片，同时用 Pillow 或 Skia 绘制头像拼图或数据图：
>
> ```yaml
> plugins:
>   htmlrender:
>     provider: takumi
>     startup: probe
>     graphics:
>       backends: [pillow, skia] # 首项 pillow 作为默认 graphics 后端
> ```
>
> 记得同时安装对应依赖：`uv add "entari-plugin-htmlrender[takumi,pillow,skia]"`。

> [!NOTE]
>
> **只用 Python 绘图，不想装 HTML 引擎怎么办？**
>
> 保持 `provider: null` 和 `startup: off`（默认就是如此），只配置 `graphics` 即可：
>
> ```yaml
> plugins:
>   htmlrender:
>     provider: null
>     graphics:
>       backend: pillow
> ```

> [!NOTE]
>
> **业务代码依赖 `HtmlRenderer` 时，切换 Takumi 和 Playwright 要改代码吗？**
>
> 调用方式不需要改——`rasterize_html()`、`rasterize_markdown()`、`rasterize_text()`、`rasterize_template()` 和 `rasterize_prepared()` 在两个后端上是完全一致的。只需要确认你的模板内容本身符合目标后端的能力范围（例如 Takumi 不支持 JavaScript 与数学公式）。
