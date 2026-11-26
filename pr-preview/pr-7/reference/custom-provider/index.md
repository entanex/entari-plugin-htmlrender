# 开发自定义 Provider

如果你想把其他 HTML 渲染引擎接入 `entari-plugin-htmlrender`，只需实现 `entari_plugin_htmlrender.providers.sdk.RenderProvider` 协议，并通过 Python 包的 `entry_points` 暴露出来。仓库中提供了完整的最小示例：[examples/echo-provider](<https://github.com/entanex/entari-plugin-htmlrender/tree/main/examples/echo-provider>)。

## 核心契约：`RenderProvider[ConfigT]`

自定义 Provider 需要实现以下属性和方法：

| 成员 | 职责与约束 |
| --- | --- |
| `id: ProviderId` | 唯一标识符，仅允许小写 ASCII 字母、数字和 `._-`（首尾需为字母或数字）。`"takumi"` 与 `"playwright"` 为内置保留名。 |
| `parse_config(raw)` | 严格解析用户的 `provider_config`（拒绝未知键），返回强类型 `ConfigT`。框架会把同一份解析对象原样传递给后续方法。 |
| `check_availability(config)` | 检查运行条件是否具备，返回 `ProviderAvailable()` 或 `ProviderUnavailable(reason, retryable=False)`。**禁止执行网络或进程 I/O**。 |
| `resource_strategy(config)` | 声明该后端需要哪种资源传递策略：`LocalResourceStrategy` 或 `RemoteResourceStrategy`。 |
| `compose(config, dependencies)` | 组装并返回 `ProviderBinding`。**禁止执行 I/O**；通过 `dependencies` 获取框架提供的 `operation_observer`、`operation_admission`、`cache_observer`、`resources` 与可选的 `asset_publisher`。 |

### `ProviderBinding` 与执行器

`compose()` 返回的 `ProviderBinding` 包含三部分：

- `lifecycle: RuntimeLifecycle`：实现 `startup()`、`probe()`、`aclose()` 三个异步方法。
- `prepared_html_executor: PreparedHtmlExecutor | None`：实现 `async execute(prepared: PreparedHtml, options: RasterOptions, *, operation: RenderOperation, materialization_policy: ResourceMaterializationPolicy | None = None) -> RenderedImage`。
- `provider_capabilities: CapabilityCatalog | None`：可选，用于向 `service.capabilities` 注册专属能力（配合 `CapabilityKey(name, Protocol)`）。

## 生命周期硬性约束

为保证插件在并发和热重载下的稳定性，自定义 Provider 的 `lifecycle` 必须满足以下要求：

1. **不在 `check_availability` / `compose` 中做 I/O**：真正启动子进程或建立网络连接只能在 `startup()` 或首次获准执行的渲染操作（当 `startup: off` 时）中发生。
2. **`startup()` 需保证原子性与并发安全**：如果初始化中途失败，必须把已申请的资源清理干净，之后允许重试；若回滚本身失败，应抛出 `ProviderLifecycleError`。
3. **`probe()` 只做校验，不改变资源所有权**。
4. **`aclose()` 必须幂等**：无论当前处于未启动、已启动还是部分初始化状态，重复调用 `aclose()` 都不应报错，并需等待活跃任务与租约排空。
5. **不越界访问宿主**：Provider 不能自行读取 Entari 配置、创建全局监控对象或直接访问宿主的内部服务。

## 注册与发现

在你的自定义 Provider 包的 `pyproject.toml` 中声明 entry point，分组名称必须为 **`entari_plugin_htmlrender.providers.v2`**，且键名与 `provider.id` 完全一致：

```toml
[project.entry-points."entari_plugin_htmlrender.providers.v2"]
echo = "echo_provider:create_provider"
```

安装该包后，用户即可在 Entari 配置中直接写 `provider: echo`。

在单元测试中，也可以不安装 entry point，直接通过 `build_runtime_plan(config, provider_override=my_provider)` 注入并验证你的 Provider。
