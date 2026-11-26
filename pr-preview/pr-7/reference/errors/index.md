# 错误类型与处理

插件定义了一套语义化的异常体系，全部继承自 `HtmlRenderError`（可从 `entari_plugin_htmlrender.errors` 导入），并附带受控长度的错误原因链 `causes: tuple[ErrorCause, ...]`。

## 异常继承关系

```
flowchart LR
    BASE["HtmlRenderError"] --> INPUT["InvalidRenderInputError"]
    BASE --> UNSUP["UnsupportedOperationError"]
    UNSUP --> UNSUP_OPT["UnsupportedRasterOptionError"]
    UNSUP --> UNSUP_FEAT["UnsupportedDocumentFeatureError"]
    BASE --> TIMEOUT["RenderTimeoutError"]
    BASE --> LIMIT["RenderOutputLimitError"]
    BASE --> RT["RuntimeUnavailableError"]
    BASE --> CAP["CapabilityUnavailableError"]
    BASE --> PROV["ProviderError"]
    PROV --> P_SEL["ProviderSelectionError\nNotFound / Conflict / Configuration"]
    PROV --> P_UNAVAIL["ProviderUnavailableError"]
    PROV --> P_EXEC["ProviderExecutionError"]
    PROV --> P_LIFE["ProviderLifecycleError"]
    BASE --> RES["ResourceError"]
    RES --> R_NF["ResourceNotFoundError"]
    RES --> R_DENY["ResourceAccessDeniedError"]
    RES --> R_BIG["ResourceTooLargeError"]
    RES --> R_FETCH["ResourceFetchError\nNetwork / Timeout / RemoteResponse / Auth"]
    RES --> R_PUB["ResourcePublishError"]
    BASE --> GFX["GraphicsError"]
    GFX --> G_UNAVAIL["GraphicsBackendUnavailableError"]
    GFX --> G_RASTER["RasterBackendExecutionError"]
    GFX --> G_DRAW["DrawingBackendExecutionError"]
```

## 异常分组说明

### 输入、能力与限额

| 异常 | 关键属性 | 常见触发场景 |
| --- | --- | --- |
| `InvalidRenderInputError` | `operation`, `field` | 传入非法宽高、非法 `TemplateRef`、`quality` 越界，或对同一 `RuntimePlan` 重复调用 `build_runtime()` |
| `UnsupportedOperationError` | `operation`, `provider_id` | 当前后端不支持该渲染操作 |
| `UnsupportedRasterOptionError` | `option`, `value` | 当前后端不支持某个 `RasterOptions` 参数值 |
| `UnsupportedDocumentFeatureError` | `feature` | 文档包含后端不支持的特性（例如把含数学公式/JS 的文档交给 Takumi） |
| `RenderTimeoutError` | `operation`, `timeout_seconds` | 渲染超过单次超时时间 |
| `RenderOutputLimitError` | `operation`, `limit`, `actual`, `maximum` | 输出像素、自动高度或文件体积超出 `html.*` / `graphics.*` 预算 |
| `RuntimeUnavailableError` | `state`, `operation` | 使用了已关闭/重载失效的服务对象，或插件启动失败 |
| `CapabilityUnavailableError` | `capability` | 访问未启用的引擎专属能力（如在 Takumi 模式下访问 `capabilities.playwright`） |

### Provider 异常（`ProviderError`）

均带有 `provider_id`、`operation`、`retryable` 属性：

- `ProviderNotFoundError` / `ProviderConflictError` / `ProviderConfigurationError`：配置的 `provider` 未找到、名称冲突或 `provider_config` 校验失败。
- `ProviderUnavailableError`（含 `reason`）：运行时依赖不可用（如浏览器缺失、远程地址无法连接或版本不匹配）。
- `ProviderExecutionError`：渲染执行期报错（例如 Takumi 动图帧率超限、底层渲染崩溃）。
- `ProviderLifecycleError`：启动或清理阶段发生不可恢复的生命周期错误。

### 资源异常（`ResourceError`）

均带有 `reference`、`operation`、`retryable` 属性：

- `ResourceNotFoundError`：本地文件、包资源或模板不存在。
- `ResourceAccessDeniedError`：路径不在 `allowed_paths` 内、软链越界，或远程地址命中黑名单/内网拦截。
- `ResourceTooLargeError`（含 `actual_size`, `maximum_size`）：单个资源超过 `resources.cache.max_resource_bytes`。
- `ResourceFetchError` 及其子类（`ResourceNetworkError`、`ResourceTimeoutError`、`ResourceRemoteResponseError`、`ResourceAuthenticationError`）：远程 HTTP 拉取失败。
- `ResourcePublishError`：Filehost 临时发布失败。

### 绘图异常（`GraphicsError`）

均带有 `backend`、`operation`、`retryable` 属性，外加绘图定位专用异常：

- `GraphicsBackendUnavailableError`（含 `reason`）：未启用或未安装 Pillow / Skia（或 Skia 缺少系统库）。
- `RasterBackendExecutionError`：`RasterScene` 执行编码失败。
- `DrawingNotFoundError` / `DrawingLoadError` / `DrawingBackendExecutionError`：绘图名未配置、源码加载或签名校验失败、绘图函数内部抛错。
