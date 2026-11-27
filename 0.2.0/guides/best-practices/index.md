# 生产最佳实践

把 `entari-plugin-htmlrender` 部署到生产环境时，遵循下面几条经验可以避免绝大多数内存泄漏、重载报错和安全隐患。

## 1\. 遵循依赖注入边界，不缓存服务对象

Entari 支持插件热重载与动态禁用/启用。每次重载都会创建新一轮的运行时，并关闭旧的服务实例。

- **推荐做法**：在事件处理函数中通过依赖注入接收细粒度接口（如 `HtmlRenderer`、`TemplateRenderer`、`DrawingRenderer`），或者接收 `HtmlRenderService`。
- **禁止做法**：不要把 `HtmlRenderService`、`HtmlRenderer`、`HtmlPreparer` 或 `capabilities` 赋值给模块级全局变量。一旦插件重载，旧对象会进入关闭状态，后续调用全部抛出 `RuntimeUnavailableError`。

```python
# ✅ 推荐：业务函数只声明自己真正需要的接口
async def render_rank(renderer: HtmlRenderer, rows: list[dict]) -> bytes:
    img = await renderer.rasterize_template(
        TemplateRef(Path("templates"), "rank.html"),
        {"rows": rows},
    )
    return bytes(img)
```

## 2\. 合理配置并发与预算上限

图片渲染属于 CPU / 内存密集型操作，务必结合服务器规格设置限流与像素上限：

```yaml
plugins:
  htmlrender:
    provider: takumi
    startup: probe
    html:
      max_concurrency: 2          # 同时进行的 HTML 渲染数
      max_pixels: 16777216        # 单图最大像素数（默认 1600 万像素）
      max_auto_height: 16384      # 自动高度上限（防长图撑爆内存）
      max_output_bytes: 67108864  # 单图最大体积 64 MiB
    graphics:
      max_concurrency: 2          # 每个绘图后端（Pillow / Skia）独立计数
      max_pixels: 16777216
```

> [!TIP]
>
> **预算超限不会静默截断**
>
> 当输出像素、自动高度或文件体积超出预算时，插件会明确抛出 `RenderOutputLimitError`，而不会静默裁剪图片。业务侧可以捕获该异常并提示用户缩小范围或分页展示。

## 3\. 让缓存真正生效

插件内部维护了 4 类独立缓存，均随插件生命周期自动清理：

| 缓存名称（监控标签） | 作用 | 调优建议 |
| --- | --- | --- |
| `resource` | 本地/远程资源内容缓存 | 调大 `resources.cache.max_bytes` 减少重复磁盘/网络读取；频繁变动的资源可传 `refresh=True` |
| `template_environment` | Jinja2 `Environment` 与模板编译缓存 | 尽量复用固定函数作为 `filters`，避免每次传匿名 `lambda` 导致缓存失效 |
| `filehost` | 远程浏览器用的临时文件托管缓存 | 配置 `prewarm_paths` 预热常用静态素材，按内存调整 `max_bytes`（默认 256 MiB） |
| `takumi_compiled` | Takumi HTML 编译结果缓存 | 通过 `provider_config.compiled_cache_max_entries`（默认 128）控制条目数 |

此外，Takumi 引擎内部还有独立的资源缓存（`cache_max_bytes`，默认 64 MiB）和字体缓存（`font_cache_max_bytes`）。容器化部署时如果字体文件随镜像只读打包，可以将字体 `cache_policy` 设为 `immutable` 以减少文件变更检查开销。

## 4\. 严守安全与日志脱敏红线

- **白名单最小化**：`resources.local_access.allowed_paths` 只添加确实存放模板、素材和字体的子目录，切勿在生产环境开启 `allow_any_path: true`。
- **保护内网地址**：保持 `resources.remote_access.allow_private_networks` 为空，仅在明确需要访问特定内网素材服务时填写精确 IP/CIDR，并配合 `allow_hosts` 限制域名。
- **区分可信与不可信内容**：渲染用户输入时，优先用 `rasterize_text()`；若必须使用 Markdown 或 HTML，请先完成 HTML 净化。
- **日志脱敏**：不要在日志或错误上报中打印原始 `provider_config`（可能含代理/远程连接令牌）、完整 HTML、模板变量、Filehost 认证头或未经清理的异常上下文（`ErrorCause`）。

## 5\. 上线前核对清单

- [ ] `startup` 已设为 `probe`，确保启动阶段就能发现后端不可用或字体缺失
- [ ] 使用 Takumi 时已配置中文字体，并实际渲染过中文测试图
- [ ] 使用 Playwright 时优先部署了独立的远程浏览器服务，且双端 Playwright 版本一致
- [ ] 所有自定义 `lease_*()` 调用均放在 `async with` 中，没有泄漏到外部作用域
- [ ] 敏感配置（远程连接地址令牌、Filehost 密钥、Sentry DSN）已通过环境变量注入，未写入仓库
