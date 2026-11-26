# 资源访问、Filehost 与安全

插件默认采用「最小权限」原则：既不允许读取未授权的本地文件，也不允许访问内网 IP。本页介绍如何安全地配置本地/远程资源、内置 Filehost 以及监控指标。

## 本地文件访问白名单

配置路径：`resources.local_access`

```yaml
plugins:
  htmlrender:
    resources:
      local_access:
        allow_any_path: false # (1)!
        allowed_paths:
          - templates
          - assets
          - fonts
```

1. **强烈建议保持 `false`**。设为 `true` 会允许读取进程可见的任意本地文件，仅限绝对可信的本地测试环境。
2. 传入 `TemplateRef.root`、当前工作目录或 HTML `<base>` 均\*\*不会\*\*自动授予文件读取权限，必须显式加入 `allowed_paths`。
3. 每次读取（包括 Jinja2 的 `include` / `extends` / `import`）都会解析符号链接后的真实路径，缓存命中也不会跳过权限校验。

## 远程访问与内网防护

配置路径：`resources.remote_access`

```yaml
plugins:
  htmlrender:
    resources:
      remote_access:
        allow_hosts:
          - cdn.example.com
        deny_hosts:
          - blocked.cdn.example.com
        allow_private_networks: [] # (1)!
        max_redirects: 5
        request_timeout_seconds: 30.0
        max_concurrent_fetches: 8
```

1. 必须填写具体的 IPv4/IPv6 地址或 CIDR 网段列表（如 `["10.0.0.0/8"]`），不接受布尔值 `true`/`false`。

### 校验规则

- **域名过滤**：`allow_hosts` 为空时不限制域名；非空时只放行列表中的域名及其子域名。`deny_hosts` 优先级永远高于 `allow_hosts`。
- **内网拦截**：默认拦截所有回环地址（`127.0.0.0/8`、`::1`）、RFC 1918 私网、链路本地地址、CGNAT（`100.64.0.0/10`）及 IPv6 ULA。即使域名在 `allow_hosts` 中，如果解析到内网 IP 仍会被拦截，除非对应网段也列入 `allow_private_networks`。
- **重定向逐跳校验**：每一跳重定向都会重新检查域名与解析后的真实 IP。

## 内置文件托管（Filehost）

仅当你使用 **远程 Playwright** 且将 `remote_local_resource_policy` 设为 `filehost` 时，才需要启用 Filehost。它会启动一个\*\*独立的 aiohttp HTTP 服务\*\*（不复用 Entari 的 HTTP 路由），专门向远程浏览器提供带租约和认证头的临时文件。

先安装可选依赖：

```bash
uv add "entari-plugin-htmlrender[filehost]>=0.2.0"
```

### 关键配置（`resources.filehost`）

```yaml
plugins:
  htmlrender:
    resources:
      filehost:
        bind_host: "127.0.0.1"
        bind_port: 8080
        public_base_url: "https://assets.example.com/htmlrender" # (1)!
        request_header_name: "X-HTMLRender-Filehost-Request"
        request_header_value: ${{ env.FILEHOST_SECRET }}         # (2)!
        cache_ttl_seconds: 300.0
        max_entries: 256
        max_bytes: 268435456 # 256 MiB
        prewarm_enabled: true
        prewarm_max_files: 256
        prewarm_paths: [assets]
        prewarm_extensions: [".png", ".jpg", ".woff2"]
```

1. **必填**：启用 Filehost 时必须显式指定远程浏览器可访问的绝对 URL，插件绝不会从监听地址或 `Host` 头自动推断。
2. 多副本部署或需要轮换密钥时，请显式配置密钥；未设置时会尝试通过 `py-machineid` 派生默认值。

> [!WARNING]
>
> **反向代理注意事项**
>
> 如果 Filehost 前方有 Nginx / Caddy 等反向代理，务必确保代理把 `request_header_name` 指定的请求头原样转发到 Filehost 后端。此外，Satori 的 `upload.create` 不具备租约、TTL 与确定性清理机制，不能替代 Filehost。

## 缓存与遍历参数

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `max_entries` | `256` | 最大缓存条目数（`>=0`） |
| `max_bytes` | `67108864` (64 MiB) | 缓存总字节上限 |
| `max_resource_bytes` | `67108864` (64 MiB) | 允许加载的单个资源最大字节数 |
| `revalidate_seconds` | `1.0` | 资源重新校验间隔（秒） |

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `environment_cache_max_entries` | `64` | Jinja2 `Environment` 实例缓存数 |
| `environment_compiled_cache_size` | `256` | 单个环境的已编译模板缓存大小（`0` 表示关闭） |

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `max_nodes` | `10000` | 解析模板变量树时的最大节点数 |
| `max_depth` | `64` | 最大嵌套层级 |
| `max_concurrency` | `16` | 并发解析资源的最大协程数 |

## 可观测性与监控

插件支持按需接入 **Prometheus** 指标与 **Sentry** 性能追踪，开启前需安装对应可选依赖（`[prometheus]` 或 `[sentry]`）；若开启开关但未安装依赖，插件会自动降级为空操作并输出提示日志，不会影响正常启动。

```yaml
plugins:
  htmlrender:
    observability:
      prometheus: true
      sentry: false
```

导出指标均采用低基数标签（`op`、`backend`、`status`）：

| 监控项 | Prometheus 指标名 | Sentry 指标名 |
| --- | --- | --- |
| 操作次数 | `entari_htmlrender_operations_total` | `entari.htmlrender.count` |
| 执行耗时 | `entari_htmlrender_duration_seconds` | `entari.htmlrender.duration` |
| 缓存事件 | `entari_htmlrender_cache_events` | `entari.htmlrender.cache.events` |
| 缓存条目数 | `entari_htmlrender_cache_entries` | `entari.htmlrender.cache.entries` |
| 缓存占用字节 | `entari_htmlrender_cache_resident_bytes` | `entari.htmlrender.cache.resident_bytes` |
