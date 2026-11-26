---
title: Takumi 配置与字体
description: 配置 Takumi 原生渲染引擎、加载中文字体与子集、调优缓存及了解平台与 CSS 边界
icon: lucide/cpu
---

# Takumi 配置与字体

**Takumi** 是基于 Rust (`takumi-py>=0.4.0`) 的进程内原生渲染引擎，不需要安装任何浏览器即可将静态 HTML、Markdown、纯文本与 Jinja2 模板渲染为图片。

```bash
uv add "entari-plugin-htmlrender[takumi]>=0.2.0"
```

## 字体配置 { #fonts }

Takumi 默认自带的字体仅覆盖基础拉丁字符，**渲染中文、日文或 Emoji 前必须手动配置字体**，并将字体目录加入本地白名单：

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    resources:
      local_access:
        allowed_paths:
          - fonts      # (1)!
          - templates
    provider_config:
      font_families:   # (2)!
        - Noto Sans SC
      fonts:
        - path: fonts/NotoSansSC-Regular.ttf
          name: Noto Sans SC
          weight: 400
          generic_family: sans-serif
```

1. 字体文件受本地访问策略保护，所在目录必须列入 `allowed_paths`。系统字体名称不会自动授权或加载。
2. 设置默认回退字体族列表（也可传逗号分隔的字符串）。

### 多字集（`unicode_range`）配置

如果一个字体家族被拆成了多个子集文件（例如拉丁 + 简体中文 + 符号），给它们配置相同的 `name`，并用 `unicode_range` 指定各自的码点闭区间 `[start, end]`（`0x0` 到 `0x10FFFF`）：

```yaml
provider_config:
  fonts:
    - path: fonts/NotoSansSC-Latin.woff2
      name: Noto Sans SC
      unicode_range: [[0x0000, 0x00FF]]
    - path: fonts/NotoSansSC-CJK.woff2
      name: Noto Sans SC
      unicode_range: [[0x4E00, 0x9FFF], [0x3000, 0x303F]]
```

!!! warning "不要省略 `unicode_range`"
    如果两个字体条目同名且字重/样式相同，但未配置 `unicode_range`，后注册的字体会直接覆盖前者。旧字段 `subset_of` 已弃用，请迁移为同名 `name` + `unicode_range`。

### 字体缓存策略

- `font_cache_policy`（默认 `"revalidate"`）：每次构建时校验字体文件变化。如果字体打包在只读容器镜像中，可在全局或单条字体上设为 `"immutable"` 以减少检查开销。
- 注意：已在运行中的 Takumi 渲染器不会热替换已注册字体，更换字体文件后需要重载插件。

---

## `provider_config` 完整参考

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `load_default_fonts` | `bool` | `true` | 是否加载 Takumi 内置默认字体 |
| `fonts` | `list` | `[]` | 字体配置列表（每项支持 `path`、`name`、`weight`、`style`、`generic_family`、`unicode_range`、`cache_policy`） |
| `font_families` | `list[str]` | `[]` | 默认字体族顺序 |
| `font_cache_policy` | `"revalidate" \| "immutable"` | `"revalidate"` | 字体文件的默认缓存策略 |
| `max_concurrency` | `int` | `min(CPU核数, 4)` | Takumi 内部执行并发数（`1..64`） |
| `compiled_cache_max_entries` | `int` | `128` | 插件层 HTML 编译结果缓存条目上限（`0..4096`） |
| `compiled_cache_max_source_bytes` | `int` | `33554432` (32 MiB) | 编译缓存允许缓存的 UTF-8 源码总字节上限 |
| `cache_max_bytes` | `int \| None` | `None` | Takumi 原生资源缓存上限（`None` 使用上游默认 64 MiB，`0` 表示不保留） |
| `font_cache_max_bytes` | `int \| None` | `None` | 动态 `cache_font()` 的 LRU 淘汰预算（`None` 不限制；已固定 `pin` 的字体不计入淘汰） |
| `default_lang` | `str \| None` | `None` | 文档默认语言标签（如 `"zh-CN"`） |
| `html_options` | object | 见下方 | 传递给 Takumi 的 HTML 解析选项 |

`html_options` 子字段：

- `presets`：`"chromium"`（默认）或 `"none"`，控制是否启用类 Chromium 的默认标签样式。
- `tailwind_property`：`str | None`，自定义 Tailwind 属性名。
- `max_depth`：`int | None`（`>=1`），限制 DOM 最大嵌套深度。

---

## HTML / CSS 支持边界

Takumi 并非完整浏览器，编写模板时需注意以下限制：

| 特性 | Takumi 支持情况 | 替代方案 |
| --- | --- | --- |
| JavaScript | ❌ 不支持 | 改用 [Playwright](playwright.md) |
| Markdown 数学公式 | ❌ 不支持（抛出 `UnsupportedDocumentFeatureError`） | 改用 Playwright 或预渲染为静态 SVG |
| `<link rel="stylesheet">` / `@import` / `@font-face` | ❌ 不支持 | 使用 `<style>` 内联（Jinja2 可用 `<style>{% include "style.css" %}</style>`）；字体通过 `provider_config.fonts` 注册 |
| 排版期自动请求网络图片 | ❌ 不支持 | 先用 `ResourceAccess.fetch_bytes()` 下载，再作为模板变量或 `PreparedAsset` 传入 |
| 上游 `Document` / `RasterImage` / MathJax API | ❌ 未接入 | 使用插件提供的 `HtmlRenderer` 与 `TakumiCapability` |

---

## 平台要求 { #platform-requirements }

`takumi-py>=0.4.0` 为 CPython 3.11+ 提供 ABI3 预编译 wheel，主流平台安装时**不需要** Rust 工具链：

- **Linux**：`manylinux2014`（glibc 2.17+）与 `musllinux` 1.2+，支持 `x86_64` 与 `aarch64`
- **macOS**：macOS 11+ (Apple Silicon) 与 macOS 10.12+ (Intel)
- **Windows**：`x86_64` 与 `ARM64`

如果在没有对应预编译包的平台上回退到源码编译，需要本机具备 Rust 1.91+、Python 开发头文件及 C/C++ 编译工具链。
