---
title: 从 0.1 升级到 0.2
description: 0.2 版本的破坏性变更清单与迁移步骤
icon: lucide/arrow-up-circle
---

# 从 0.1 升级到 0.2

`0.2.0` 对底层架构、依赖拆分、网络安全策略与数学公式解析进行了重要重构。请按下方清单逐项核对迁移。

## 升级核对清单

- [ ] 升级运行环境：Python `>=3.11, <4.0`，Entari `>=0.19.4, <0.20.0`
- [ ] 在安装命令中显式添加所需的渲染后端可选依赖（如 `[takumi]`、`[playwright]`）
- [ ] 检查配置中的 `resources.remote_access.allow_private_networks`，把布尔值改为 IP/CIDR 列表
- [ ] 检查 Markdown 数学公式写法（行内 `$x$` 两端不再允许空格，块级 `$$...$$` 需独占段落）
- [ ] 检查业务代码，不要将 `HtmlRenderService` 或 `HtmlRenderer` 缓存在模块全局变量中

---

## 逐项变更说明

### 1. 运行环境基线提高

| 项目 | 0.1.x | 0.2.x |
| --- | --- | --- |
| Python | `>=3.10` | `>=3.11, <4.0`（使用标准库 `ExceptionGroup`） |
| Entari | `0.18.x` | `>=0.19.4, <0.20.0` |

### 2. 渲染后端改为按需安装

在 `0.2.0` 中，基础包不再捆绑任何浏览器或渲染引擎。你需要根据需求显式安装附加依赖：

```bash
# 静态渲染（推荐迁移目标，无需浏览器）
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"

# 需要浏览器能力时
uv add "entari-plugin-htmlrender[playwright]>=0.2.0"
```

如果你打算把原有的静态模板从 Playwright 迁移到 Takumi：

1. 将 `provider` 改为 `takumi`，移除原有的 Playwright `provider_config`。
2. 配置中文字体，并将字体与模板目录加入 `resources.local_access.allowed_paths`。
3. 将模板中的 `<link rel="stylesheet">` 改为 `<style>` 内联（Jinja2 可用 `<style>{% include "style.css" %}</style>`）。

### 3. 内网访问控制改为显式 IP/CIDR 列表

`resources.remote_access.allow_private_networks` **不再接受布尔值 `true` / `false`**，必须显式填写允许访问的 IP 或 CIDR 网段（默认为空，拒绝所有内网地址）。

同时，`allow_hosts` 不再自动放行内网 IP。如果某个内网域名既在域名白名单里、又解析到内网地址，必须同时放行对应网段：

=== "0.2 正确写法"

    ```yaml
    plugins:
      htmlrender:
        resources:
          remote_access:
            allow_hosts:
              - assets.internal
            allow_private_networks:
              - "10.0.0.0/8"
              - "192.168.1.0/24"
    ```

=== "0.1 旧写法（0.2 会报错）"

    ```yaml
    plugins:
      htmlrender:
        resources:
          remote_access:
            allow_private_networks: true # ❌ 0.2 校验阶段直接拒绝
    ```

### 4. Markdown 数学公式解析收紧

`0.2.0` 固定使用 `pymdownx.arithmatex(generic=True, smart_dollar=True)`：

- **行内公式**：`$x$` 要求美元符号紧贴公式内容，或者改用 `\(x\)`。像 `$ x $` 这样两端带空格的写法在 0.2 中会保留为普通文本（避免误伤价格等带美元符号的文案）。
- **块级公式**：`$$...$$`、`\[...\]` 和独立的 `\begin{env}...\end{env}` 必须独占段落，行内混写的 `before $$x$$ after` 不再视为块级公式。
- **KaTeX 作用域**：Playwright 内置的 KaTeX 脚本只渲染由 Markdown 解析器生成的 `.arithmatex[data-htmlrender-arithmatex]` 容器，不会扫描原始 HTML 中手写的 `.arithmatex` 元素。
- **Takumi 限制**：含数学公式的文档会标记为需要 JavaScript；交给 Takumi 渲染会直接抛出 `UnsupportedDocumentFeatureError`。需要公式渲染请使用 Playwright，或提前将公式预渲染为静态 HTML/SVG。

### 5. 服务入口与依赖注入

`HtmlRenderService` 现在统一提供 7 个公开属性：`preparation`、`renderer`、`templates`、`resources`、`graphics`、`drawings` 和 `capabilities`。其中前 6 个接口也可以直接通过 Entari 依赖注入获取。

此外新增了 `HtmlPreparer`（`service.preparation`），支持先把 Markdown、模板或文本准备为中立的 `PreparedHtml`，再交给任意渲染后端执行。

### 6. 独立的 Python 绘图能力

Pillow 与 Skia 不再归属于 HTML Provider，而是独立的 `graphics` 配置项：

- 可通过 `graphics.backends: [pillow, skia]` 同时启用多个绘图后端。
- 新增 `graphics.drawings`（对应 `DrawingRenderer`），可直接注册和热重载 Python 绘图函数。

### 7. Takumi 0.4 接口调整

- 依赖升级为 `takumi-py>=0.4.0`。
- 字体子集配置中，`subset_of` 已弃用，请改用相同的 `name` 配合 `unicode_range` 区间区分不同字集。
- `lease_api()` 新增编译缓存、布局测量、动图编码（WebP/APNG 最高 90 FPS，GIF 最高 50 FPS）与动态字体缓存接口，并新增 `cache_max_bytes` 和 `font_cache_max_bytes` 配置项。

### 8. 扩展与底层嵌入变更

如果你开发了自定义 Provider 或绕过 Entari 直接组装运行时，需要注意：

- 第三方 Provider 的 entry point 分组更新为 `entari_plugin_htmlrender.providers.v2`。
- 直接实例化 `RenderRuntime(...)` 时，现在必须显式传入 `preparer: HtmlPreparer`。
- 自定义的 `HtmlPreparer`、`TemplateRenderer` 或 `HtmlRenderer` 实现，其模板相关方法必须接受 `filters` 与 `extensions` 关键字参数。
