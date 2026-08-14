---
title: HTML 渲染预算
description: 跨 Provider 一致实施的 HTML 输入与并发限制
---

# HTML 渲染预算

`html` 设置由 composition 统一实施，位于具体 executor 外层：

| 键 | 默认值 |
| --- | ---: |
| `html.max_source_bytes` | `67108864` |
| `html.max_pixels` | `16777216` |
| `html.max_output_bytes` | `67108864` |
| `html.max_device_pixel_ratio` | `4.0` |
| `html.max_auto_height` | `16384` |
| `html.max_concurrency` | `2` |

预算适用于 `HtmlRenderer.rasterize_html/text/markdown/template/prepared`。切换Playwright、Takumi 或第三方 Provider 不改变拒绝语义：输入或 raster option 无效时抛出 `InvalidRenderInputError`；Provider 输出超过字节、像素或自动高度限制时抛出`RenderOutputLimitError`。所有路径都拒绝而不静默截断。
