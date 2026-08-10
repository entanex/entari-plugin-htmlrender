---
title: Runtime API
description: RenderRuntime、HtmlRenderer、RuntimeResolver 与 Entari 服务生命周期
---

# Runtime API

`RenderRuntime` 是一次 composition 的 host-neutral 聚合根，暴露：

| 属性 | 语义 |
| --- | --- |
| `renderer: HtmlRenderer` | 执行跨 Provider 的 typed render request |
| `preparation` | 受 admission gate 保护的 preparation facade |
| `resources` | 受 admission gate 保护的资源 facade |
| `extensions` | Playwright、Takumi、Pillow、Skia 与第三方 typed capability |

## 显式解析

`RuntimeSource` 是 `RenderRuntime | RuntimeResolver`。`HtmlRenderService` 实现`RuntimeResolver`，因此 caller-first API 可直接接收它：

```python
from entari_plugin_htmlrender import RuntimeSource, render_html, resolve_runtime

async def render_status(runtime: RuntimeSource) -> bytes:
    active = resolve_runtime(runtime)
    image = await render_html("<b>ready</b>", runtime=active)
    return bytes(image)
```

显式 source 总是优先。省略 `runtime=` 时只读取当前 task 通过`runtime_context(source)` 绑定的 source；若两者都不存在则抛出`RuntimeNotBound`。库不提供进程全局默认 runtime、setter 或 factory。

## 生命周期

- `startup()` 幂等且并发安全；已关闭或正在关闭的 runtime 拒绝重新启动。
- `probe()` 先确保 startup 完成，再执行 Provider 的最小探测。
- `aclose()` 停止接收新操作，等待已获准操作完成，再关闭 Provider；成功关闭后幂等，失败保持可重试，但一旦开始关闭就不能再次渲染或启动。

Entari 中不要手工驱动 service 持有 runtime 的生命周期。`HtmlRenderService` 由`add_service` 注册，并在 Launart `preparing` / `blocking` / `cleanup` 阶段管理它；热卸载同样进入 cleanup。
