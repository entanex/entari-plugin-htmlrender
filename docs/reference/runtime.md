---
title: 运行环境与 Entari 服务
description: 插件服务、手动组装与生命周期归属
---

# 运行环境与 Entari 服务

## 普通调用路径

Entari 事件处理函数通过 DI 接收 `HtmlRenderService`。服务直接提供七个稳定入口：

| 属性 | 语义 |
| --- | --- |
| `preparation: HtmlPreparer` | HTML、文本、Markdown 或模板到中立 `PreparedHtml` |
| `renderer: HtmlRenderer` | HTML、文本、Markdown、模板或 `PreparedHtml` 到图像 |
| `templates: TemplateRenderer` | `TemplateRef` 到 `RenderedHtml` |
| `resources: ResourceAccess` | 显式 locator fetch 与 scoped publish |
| `graphics: GraphicsRenderer` | `RasterScene` 到图像，与 HTML Provider 独立 |
| `drawings: DrawingRenderer` | 按配置名称执行受信任的 Python 绘图函数 |
| `capabilities: RuntimeCapabilities` | Playwright、Takumi 与第三方后端的类型化操作入口 |

```python
from entari_plugin_htmlrender import RasterOptions, RenderedImage
from entari_plugin_htmlrender.entari import HtmlRenderService

async def render_status(service: HtmlRenderService) -> RenderedImage:
    prepared = await service.preparation.prepare_html("<strong>ready</strong>")
    return await service.renderer.rasterize_prepared(
        prepared,
        raster=RasterOptions(width=640, device_pixel_ratio=1),
    )
```

框架无关函数应直接接收它真正需要的 `HtmlPreparer`、`HtmlRenderer`、`TemplateRenderer`、`ResourceAccess`、`GraphicsRenderer` 或 `DrawingRenderer` 接口；依赖解析只发生在 Entari DI 边界。这些接口的实例都属于当前插件生命周期，不能存入模块级单例。

Python 绘图也可以直接注入 `DrawingRenderer`。它的 `.names` 返回本次配置公开的 `frozenset[str]`；`render()` 接受名称、映射数据、物理像素尺寸、背景和输出选项。`service.drawings` 指向同一实例：

```python
from entari_plugin_htmlrender.graphics import DrawingRenderer

async def render_profile(drawings: DrawingRenderer):
    return await drawings.render(
        "profile",
        {"name": "Ada"},
        width=640,
        height=360,
    )
```

源码预加载、共享模块、`reload` 语义、显式 `await drawings.reload("profile")`、画布类型和代码安全说明见 [绘图后端配置](../configuration/graphics/index.md)。

Entari 事件处理函数也可以直接注入这些接口，而不必先接收整个服务：

```python
from entari_plugin_htmlrender import HtmlPreparer

async def prepare_status(preparation: HtmlPreparer):
    return await preparation.prepare_html("<strong>ready</strong>")
```

插件加载时会把 `HtmlRenderer`、`TemplateRenderer`、`HtmlPreparer`、`ResourceAccess`、`GraphicsRenderer` 与 `DrawingRenderer` 注册到 Letoderea DI。依赖提供器从 Launart 当前活动服务取得对应实例，因此已编译 handler 在插件重载后仍会取得新实例；插件卸载时对应提供器也会移除。

## 绘图模块的生命周期

Entari 宿主先将绘图所在真实 Python 包的模块声明为独立插件，再按实际导入关系使用 `load_plugin` 加载。声明本身不执行未被导入的源码。绘图和辅助模块使用正常的模块名，共享实例、引用关系和重载传播由框架管理。每次渲染从当前可用插件取得函数；禁用或卸载后不会继续调用缓存的旧入口。

`reload: true` 的源码检查最终调用 `reload_plugin` / `reload_subplugin`。语法或模块导入失败时，框架保留旧插件。模块成功加载后出现无效入口或绘图执行异常，会直接报错；这不提供整张依赖图的事务回滚。

宿主通过 `keeping` 保留一份共享的源码使用记录。配置重载时，新运行时先取得所需源码，旧运行时等待已接纳任务完成后释放引用。只清理自己加载且无人使用的插件；原有外部插件和仍被其他插件引用的源码会保留。

配置重载时，导入、配置校验或运行时构建失败会保留旧插件。新插件替换成功后才进入 Launart 服务的启动和探测阶段，该阶段失败不会恢复旧插件。部署前可用 `startup: off` 验证配置，再按需要开启启动探测。

## 手动组装运行时

`RenderRuntime` 管理一次完整渲染环境的生命周期。普通业务函数使用注入的接口；框架适配器或独立应用可以自行创建和关闭运行时：

```python
from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig

config = HtmlRenderConfig.model_validate({"provider": "playwright", "startup": "off"})
plan = build_runtime_plan(config)
runtime = plan.build_runtime()
server = plan.hosted_asset_server

try:
    if server is not None:
        await server.startup()
    await runtime.startup()
    image = await runtime.renderer.rasterize_html("<b>ready</b>")
finally:
    try:
        await runtime.aclose()
    finally:
        if server is not None:
            await server.aclose()
```

默认构建过程不执行外部 I/O；自定义绘图注册表工厂可以在构建时读取源码并加载插件。`RuntimePlan` 是 one-shot ownership value，`build_runtime()` 恰好调用一次；第二次调用抛出 `InvalidRenderInputError(operation="runtime.build", field="plan")`，需要另一个 runtime 时应重建 plan。Provider-owned parsed config 在 plan → availability → compose 期间保持同一 identity。若 resource strategy 需要 filehost，计划持有的 server 与生成的唯一 runtime 同寿命：创建方先启动 `hosted_asset_server`，关闭时先排空 runtime，再关闭 server。

测试或 embedding 若要绕过 entry-point discovery，可传配置所选的单个 Provider：

```python
plan = build_runtime_plan(config, provider_override=provider)
```

该参数不是候选列表；override 的 ID 必须与 `config.provider` 一致。

宿主也可以通过工厂函数注入绘图源码注册表。省略该参数时，使用独立的模块加载方式：

```python
runtime = plan.build_runtime(
    drawing_registry_factory=host_registry_factory,
)
```

注册表实现 `DrawingSourceRegistry`：通过 `names` 和 `spec()` 查询配置，用 `lease()` 提供绘图函数，提供 `reload()` 和 `aclose()` 管理重载及关闭。工厂接收源码定义和工作线程执行器；Entari 的插件依赖管理通过这个接口接入。

## Runtime 生命周期

- 初始状态为 `RuntimeState.OPEN`；`startup()` 幂等且并发安全。startup policy `off` 只跳过 eager startup，首个已获准 Provider operation 可以 lazy acquire。
- `probe()` 先确保 startup 完成，再执行 Provider 的最小探测。
- `aclose()` 先切到 `CLOSING`，永久停止新操作，等待已接纳操作完成，再关闭 Provider/resources；成功后进入 `CLOSED`。
- 排空或关闭被取消/失败时保持 `CLOSING`，后续 `aclose()` 可重试；runtime 不会重新开放。

Entari 中不要手工驱动 service 内部 runtime。`HtmlRenderService` 没有公共 `startup()` / `probe()` / `aclose()`；Launart stages 与插件热卸载拥有其生命周期。关闭开始后，`preparation`、`renderer`、`resources`、`graphics`、`drawings` 与 capability leases 都按同一 admission boundary 拒绝新工作并排空已接纳工作。
