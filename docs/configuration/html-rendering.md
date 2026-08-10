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

预算适用于 `render_html`、`render_text`、`render_markdown`、`render_template` 与`rasterize_html`。切换 Playwright、Takumi 或第三方 Provider 不改变拒绝语义；超过限制会以稳定的 `InvalidRenderRequest` 或相应 rendering error 失败，不静默截断。
