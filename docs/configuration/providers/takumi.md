---
title: Takumi 配置
description: Takumi 原生 Provider 的静态渲染、字体和 typed Capability
icon: lucide/gauge
---

# Takumi 配置与能力

Takumi 在进程内执行 Rust 原生排版，不启动浏览器，不执行 JavaScript，也不访问网络。插件正式依赖 PyPI 已发布的 `takumi-py==0.4.0`。

## 安装与选择

```bash
uv add "entari-plugin-htmlrender[takumi]>=0.2.0,<0.3"
```

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    provider_config:
      max_concurrency: 4
```

## 配置

下表字段均位于 `provider_config`：

| 完整路径 | 默认值 | 说明 |
| --- | --- | --- |
| `provider_config.load_default_fonts` | `true` | 加载 Takumi 默认字体 |
| `provider_config.fonts` | `[]` | 启动时注册的字体 |
| `provider_config.font_cache_policy` | `revalidate` | 默认字体文件 cache policy |
| `provider_config.cache_max_bytes` | `null` | native resource cache 字节预算；`null` 使用上游默认的 64 MiB，`0` 禁止保留 |
| `provider_config.font_cache_max_bytes` | `null` | `cache_font()` 字体的预算；`null` 表示无上限，`0` 不是“必定不持有” |
| `provider_config.max_concurrency` | `min(cpu_count, 4)` | native 调用并发上限，1–64 |
| `provider_config.compiled_cache_max_entries` | `128` | compiled LRU 条目上限 |
| `provider_config.compiled_cache_max_source_bytes` | `33554432` | compiled cache 的模板 source UTF-8 字节预算（非 native 常驻内存）；条目数量硬上限仍由 `compiled_cache_max_entries` 提供 |
| `provider_config.html_options.presets` | `chromium` | `chromium` 或 `none` |
| `provider_config.html_options.tailwind_property` | `null` | Tailwind 属性名 |
| `provider_config.html_options.max_depth` | `null` | parser 最大深度 |
| `provider_config.default_lang` | `null` | 默认语言 |
| `provider_config.font_families` | `[]` | 字体回退顺序 |

`fonts` 中每个条目的字段如下；未知字段会被拒绝：

| 字段 | 默认值 | 约束 |
| --- | --- | --- |
| `path` | 必填 | 非空字体文件路径 |
| `name` | `null` | 注册后的字体族名称 |
| `weight` | `null` | `1`–`1000` |
| `style` | `null` | 字体 style |
| `generic_family` | `null` | CSS generic family，如 `sans-serif`、`serif`、`monospace`、`emoji` |
| `unicode_range` | `null` | 字体负责的闭区间码位范围 `[[start, end], ...]`；每项满足 `0 <= start <= end <= 0x10FFFF` |
| `subset_of` | `null` | 兼容入口；转发为字体族 `name`，并优先于同项 `name` |
| `cache_policy` | `null` | `immutable` / `revalidate`；为空时继承 `font_cache_policy` |

字体示例：

```yaml
plugins:
  htmlrender:
    provider: takumi
    resources:
      local_access:
        allowed_paths: [/app/fonts]
    provider_config:
      load_default_fonts: false
      fonts:
        - path: /app/fonts/NotoSansSC-Regular.otf
          name: Noto Sans SC
          generic_family: sans-serif
          cache_policy: immutable
      font_families: [Noto Sans SC, sans-serif]
```

只有随镜像不可变的字体才应使用 `immutable`。运行中的 native renderer不会热替换已注册字体；文件变化后需重建 composition。字体路径同样受`resources.local_access.allowed_paths` 约束。

同一字体族的多个子集应使用相同 `name`，并分别为每个文件声明 `unicode_range`。Takumi 会按字符选择覆盖该码位的子集，而不是把子集拆成不同字体族：

```yaml
provider_config:
  fonts:
    - path: /app/fonts/Example-Latin.woff2
      name: Example Sans
      unicode_range: [[0x0000, 0x00FF]]
    - path: /app/fonts/Example-Cyrillic.woff2
      name: Example Sans
      unicode_range: [[0x0400, 0x045F]]
  font_families: [Example Sans, sans-serif]
```

`subset_of` 仍可读取已有配置，但新配置应迁移到 `name` + `unicode_range`。没有 `unicode_range` 时，后注册的同名、同描述符字体会遮蔽先前字体。

## 缓存使用与诊断

Takumi runtime 有三类独立缓存：

- 每个 native renderer 的 resource cache 保存解码后的图片、缩放变体与 SVG 栅格；`cache_max_bytes: null` 使用上游 64 MiB 默认值。重复的 `data:` URI 图片也经过该缓存。
- `cache_font()` 持有的字体受 `font_cache_max_bytes` 约束；`null` 表示无上限。font cache 按解码字体数据做 LRU 淘汰，但不是严格的进程内存峰值上限：单次 `cache_font()` 新增的字体族不会被这次调用自身淘汰，已注册字体也不参与空间释放。
- 插件自己的 compiled HTML/CSS singleflight LRU 是另一层缓存。`compiled_cache_max_source_bytes` 的单位是输入 source 的 UTF-8 bytes，不是 native heap；须同时观察条目数量上限。

```python
from entari_plugin_htmlrender.capabilities import TakumiCapability

async def cache_stats(takumi: TakumiCapability) -> tuple[int, int, int]:
    async with takumi.lease_session() as session:
        await session.render_svg_html("<strong>cached</strong>", width=320)
        stats = session.compiled_cache_stats
        return stats.hits, stats.misses, stats.evictions
```

统计只描述插件 compiled cache。公共 API 不提供 compiled cache clear；需要释放 native compiled object 或重建 native resource cache 时，由 Entari 关闭并重新加载 service。字体可通过下述 managed API 单独释放。完整调优流程见[缓存组件与调优](../../guides/cache-lifecycle.md)。

## 能力边界

Takumi 支持静态 HTML、文本、模板和大多数 Markdown；下列需求会明确失败：

- JavaScript、远程网络资源和页面导航；
- `pymdownx.arithmatex` generic 模式产生的客户端 KaTeX 排版；
- 无法在 Preparation 阶段物化的 `@import`、字体或图片；
- Provider 无法表达的 conditional stylesheet；
- 浏览器页面、User-Agent、header 与 selector 操作。

含数学公式的 `prepare_markdown()` 仍可成功完成：它注入 KaTeX 脚本并把 `DocumentRequirement.JAVASCRIPT` 加入 `PreparedHtml`。Takumi 在自己的 source inspection 阶段检测到该要求后会抛出 `UnsupportedDocumentFeatureError`（`feature="javascript"`），不会进入 native rasterization，也不会把静态 TeX 标记画成图像。若要用 Takumi 输出公式，应先把公式排版为不含 JavaScript 的静态 HTML/SVG，再通过不包含公式脚本的 preparation 流程交给 Takumi。`PreparedAsset` 直接把 bytes 交给 native renderer，不创建临时文件。

上游 `dev` 分支新增的 `Document`、`RasterImage` 与 `MathJax` API 尚未包含在 PyPI 0.4.0。插件当前不公开这些预览接口，Markdown 公式仍需选择 Playwright。

## 平台约束

项目锁定的 `takumi-py==0.4.0` 提供 CPython 3.11+ ABI3 wheel：

| 平台 | wheel |
| --- | --- |
| Linux | manylinux2014（glibc 2.17+）与 musllinux 1.2+，x86-64/AArch64 |
| macOS | macOS 11+ ARM64、macOS 10.12+ Intel |
| Windows | x86-64、ARM64 |

没有匹配 wheel 的平台会尝试源码构建，需要 Rust 1.91+、Python 开发环境和目标平台原生工具链。已在 wheel 矩阵内的安装不需要 Rust。安装环境应重新核对[PyPI 0.4.0 文件](https://pypi.org/project/takumi-py/0.4.0/#files)。

Takumi 自带的 Latin fallback 不能覆盖业务所需字符集。需要中文或其他脚本时，应通过 `provider_config.fonts` 把字体随部署交付；这属于内容资源，不是系统动态库依赖。

## typed Capability

SVG 与动态字体管理是 Takumi 专属 managed capability：

```python
from entari_plugin_htmlrender.capabilities import TakumiCapability

async def render_svg(takumi: TakumiCapability) -> str:
    async with takumi.lease_session() as session:
        return await session.render_svg_html("<strong>Hello</strong>", width=320)
```

`register_font_file()` 同时支持 `unicode_range`。它注册的字体在 runtime 生命周期内保持 pinned，使用 `lease_api().unregister_font()` 或 `clear_fonts()` 可以显式释放。按需加载的字体应使用 `cache_font()` / `cached_fonts()`；后者的 `pin=True` 会阻止空间淘汰。

```python
from entari_plugin_htmlrender.capabilities import TakumiCapability

async def use_cached_font(takumi: TakumiCapability, font_bytes: bytes) -> str:
    async with takumi.lease_api() as api:
        key = "https://assets.example/font.woff2"
        families = await api.cached_fonts(key)
        if families is None:
            families = await api.cache_font(font_bytes, key)
        return await api.render_svg_html(
            "<strong>Cached font</strong>",
            font_families=families,
        )
```

`cache_font()` 的预算是淘汰依据，不是严格内存上限。更可预测的固定字体应作为 `provider_config.fonts` 提供，或用 `register_font_file()` 注册后由调用方显式释放。

`lease_session()` 绑定并持有当前有效 lease。调用方不得让 session 逃逸出上下文，也不应保存为进程级单例；已返回的 `bytes`、SVG 字符串与 cache stats snapshot 不受该限制。

需要编译、测量、节点、动画、帧编码或动态字体缓存时，使用 `lease_api()` 获得完整 `TakumiAPI`。动画的 WebP/APNG `fps` 不得超过 90，GIF 不得超过 50。`compile_html()` 返回的 `TakumiCompiledDocument` 只可在创建它的 API lease 中使用；退出 lease 后，session、API 和 compiled document 都会拒绝后续调用。完整方法见[Capability 参考](../../reference/capabilities.md#takumi)。

需要直接操作上游对象时，可通过 `lease_native_renderer()` 显式租用native renderer。该入口保留 `takumi_py.Renderer` 原生类型，调用方承担同步执行、并发、native panic、资源归一化与底层错误语义；详见[Capability 参考](../../reference/capabilities.md#takumi)。

## 选择建议

需要脚本、网页导航或浏览器布局语义时选择 Playwright；内容完全受控、希望避免浏览器进程，或需要 Takumi SVG/字体/native 能力时选择 Takumi。

启用或再分发 Takumi 前，请自行检查 `takumi-py` 当前版本的许可与平台 wheel；这里不构成法律意见。
