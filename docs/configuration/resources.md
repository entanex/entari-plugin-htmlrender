---
title: 资源与访问策略
description: 缓存、路径白名单、网络策略与显式 aiohttp filehost
---

# 资源与访问策略

本地与远程访问默认收紧：`local_access.allow_any_path=false`，私网地址默认拒绝。模板的 base 只负责解析相对引用，不会扩大允许读取的路径。

```yaml
plugins:
  htmlrender:
    resources:
      local_access:
        allowed_paths: [templates, assets]
      remote_access:
        allow_hosts: [cdn.example.com]
        deny_hosts: []
        max_redirects: 5
        request_timeout_seconds: 30
      traversal:
        max_nodes: 10000
        max_depth: 64
        max_concurrency: 16
```

每次调用可用 `ResourcePolicy.AUTO`、`STRICT` 或 `OFF` 覆盖 Provider 默认资源模式。策略在授权前执行；cache hit 不绕过路径或网络检查。

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
| `resources.remote_access.allow_private_networks` | `false` |
| `resources.remote_access.allow_hosts` | `[]` |
| `resources.remote_access.deny_hosts` | `[]` |
| `resources.remote_access.max_redirects` | `5` |
| `resources.remote_access.request_timeout_seconds` | `30.0` |
| `resources.remote_access.max_concurrent_fetches` | `8` |

直接读取可传 `refresh=True` 绕过当前 resident value 并执行重新验证。

## Filehost

需要把本地/内存资源发布给远程浏览器时安装 `filehost` extra。composition 仅在Provider 的 resource strategy 要求 filehost 时显式创建同一个`HostedAssetStore`、`FilehostAssetPublisher` 与 aiohttp
`HostedAssetHttpServer`：

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

`public_base_url` 必须是浏览器实际可达、由反向代理映射到固定内部 mount 的绝对URL；它不会从 bind 地址、`Host` 或 forwarded header 推导。请求授权随`ResourceResolution.request_headers_by_url` 绑定到精确 URL。

| 完整配置路径 | 默认值 |
| --- | ---: |
| `resources.filehost.bind_host` | `127.0.0.1` |
| `resources.filehost.bind_port` | `8080` |
| `resources.filehost.max_entries` | `256` |
| `resources.filehost.max_bytes` | `268435456` |

filehost 由 `HtmlRenderService` 在 Launart preparing 启动、cleanup 关闭，不依赖Entari 的 HTTP server 或路由 mount。
