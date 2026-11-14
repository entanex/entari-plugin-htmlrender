---
title: 资源与访问策略
description: 缓存、路径白名单、网络策略与显式 aiohttp filehost
---

# 资源与访问策略

本地与远程访问默认收紧：`local_access.allow_any_path=false`，非公网目标默认拒绝。模板的 base 只解析相对引用，不会扩大允许读取的路径。

```yaml
plugins:
  htmlrender:
    resources:
      local_access:
        allowed_paths: [templates, assets]
      remote_access:
        allow_private_networks: []
        allow_hosts: [cdn.example.com, internal.example.com]
        deny_hosts: []
        max_redirects: 5
        request_timeout_seconds: 30
      traversal:
        max_nodes: 10000
        max_depth: 64
        max_concurrency: 16
```

渲染调用通过 `ResourceMaterializationPolicy.AUTO`、`STRICT` 或 `OFF` 显式覆盖Provider 默认物化策略。策略在授权前执行；cache hit 不绕过路径或网络检查。

`allow_hosts` 限制可访问的主机名；空列表表示不限制主机名，但仍受 IP 策略约束。非空列表只允许列出的主机及其子域。`allow_hosts` 不能替代 IP 网络授权：回环、RFC 1918、链路本地、CGNAT/shared `100.64.0.0/10`、ULA 等非公网解析地址还必须匹配 `allow_private_networks` 中的 IPv4/IPv6 地址或 CIDR。`deny_hosts` 始终优先。

例如，只允许访问指定内网主机及其子域，同时授权两个 IPv4 网段和一个 IPv6 网段：

```yaml
resources:
  remote_access:
    allow_hosts: [internal.example.com]
    allow_private_networks:
      - 10.20.0.0/16
      - 127.0.0.1/32
      - fd00:1234::/48
    deny_hosts: [blocked.internal.example.com]
```

`allow_private_networks` 是**显式网络白名单**。旧版的布尔值 `true` / `false` 已不再有效；`[]` 表示不允许任何非公网解析地址，需要访问哪一网段就列出对应 IP 或 CIDR。

旧版还允许把 `allow_hosts` 当作私网绕过。升级后必须同时授权实际解析到的私网 IP/CIDR；仅保留主机名不会放行非公网地址。迁移前先解析目标并在部署网络中确认结果，再迁移到上述列表格式。

| 完整配置路径 | 默认值 |
| --- | ---: |
| `resources.cache.max_entries` | `256` |
| `resources.cache.max_bytes` | `67108864` |
| `resources.cache.max_resource_bytes` | `67108864` |
| `resources.cache.revalidate_seconds` | `1.0` |
| `resources.templates.environment_cache_max_entries` | `64` |
| `resources.templates.environment_compiled_cache_size` | `256` |
| `resources.traversal.max_nodes` | `10000` |
| `resources.traversal.max_depth` | `64` |
| `resources.traversal.max_concurrency` | `16` |
| `resources.remote_access.allow_private_networks` | `[]` |
| `resources.remote_access.allow_hosts` | `[]` |
| `resources.remote_access.deny_hosts` | `[]` |
| `resources.remote_access.max_redirects` | `5` |
| `resources.remote_access.request_timeout_seconds` | `30.0` |
| `resources.remote_access.max_concurrent_fetches` | `8` |

业务代码通过 `service.resources.fetch*()` 读取显式 `ResourceRef`。`refresh=True`跳过当前 resident value 并重新验证来源；inline bytes 已经是 payload，不伪装成可 fetch 的 locator。

## Filehost

需要把本地/内存资源发布给远程浏览器时安装 `filehost` extra。composition 仅在Provider 的 resource strategy 要求 filehost 时创建同一个 `HostedAssetStore`、`FilehostAssetPublisher` 与 aiohttp `HostedAssetHttpServer`：

```yaml
plugins:
  htmlrender:
    resources:
      filehost:
        bind_host: 127.0.0.1
        bind_port: 8080
        public_base_url: https://render-assets.example.com/_htmlrender/assets/
        cache_ttl_seconds: 300
```

`public_base_url` 必须是 Bot 实际可达、由反向代理映射到固定内部 mount 的绝对URL；它不会从 bind 地址、`Host` 或 forwarded header 推导。受管理的 Playwright rendering 由 Bot 获取该 URL 并把响应交给浏览器。私网解析地址仍须匹配 `allow_private_networks`。对业务调用者，`ResourceAccess.publish()` 建立显式租约并 yield `PublishedResource`：

```python
from entari_plugin_htmlrender.resources import InlineResource

async with service.resources.publish(InlineResource(b"payload", media_type="application/octet-stream")) as published:
    url = published.url
    headers = published.request_headers
    # url 与精确授权 headers 仅在这个作用域内有效。
```

上传过程中释放的租约不会在上传完成后重新生效。发布器会保留仍在使用资源的租约，并在协调存储状态后返回 URL。

Provider 可使用收窄资源接口的 `fetch(ResourceRef)` 读取显式 locator，或使用 `fetch_published(published)` 在 publication lease 内读取 URL-scoped capability。`fetch_published()` 每次使用 `PublishedResource` 携带的精确 URL 与请求头执行 guarded、uncached fetch；redirect 到不同 URL 时不会保留原请求头。

| 完整配置路径 | 默认值 |
| --- | ---: |
| `resources.filehost.bind_host` | `127.0.0.1` |
| `resources.filehost.bind_port` | `8080` |
| `resources.filehost.max_entries` | `256` |
| `resources.filehost.max_bytes` | `268435456` |

filehost 由 `HtmlRenderService` 在 Launart preparing 启动、cleanup 关闭，不依赖Entari 的 HTTP server 或路由 mount。

### Satori upload 不是 filehost

Satori `upload.create` 面向当前事件账号，并把资源交给外部 Satori Server 管理。其协议不提供租约、续期、显式删除、容量预算或可观察的 TTL，也无法在插件热卸载时确定性清理，因此不能实现 `AssetPublisher` 的生命周期契约。向消息平台上传最终产物时，应在 handler 中显式使用当前 `Session`；不要把该 API 当作渲染输入资源的 filehost。
