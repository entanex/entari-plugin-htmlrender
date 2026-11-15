---
title: Entari 插件生命周期与重载
description: import、RuntimePlan、HtmlRenderService、Launart stages、DI、热重载与绘图源码所有权
icon: lucide/refresh-cw
---

# Entari 插件生命周期与重载

本页面向维护 HTMLRender 的 Entari integration、诊断 generation 切换或扩展宿主边界的开发者。应用侧的配置与切换步骤见[启动与生命周期](../configuration/lifecycle.md)和[多引擎与切换](../guides/switching-engines.md)；Provider 自身的 `startup()`、`probe()` 与 `aclose()` 契约见[Provider 契约](provider-contract.md)。

本文将每次创建、运行并关闭的服务实例称为一个 generation。模块 import、`RuntimePlan`、一次完整 runtime、`HtmlRenderService`、Launart service generation、DI 解析与绘图源码引用各有独立所有者。排障时必须先判断故障发生在哪一个边界，不能把所有 reload 都当作同一种事务。

## 阶段与所有者

```text
ordinary package import
  -> caller contracts and value objects
  -> no Entari service, adapter startup, or runtime acquisition

Entari plugin load
  __plugin__ present
  -> register_plugin()
  -> build_runtime_plan()
  -> RuntimePlan.build_runtime()
  -> configured drawing sources may be read/imported here
  -> add_service(HtmlRenderService)

Launart service generation
  -> preparing
  -> blocking
  -> cleanup
```

| 边界 | 产物或行为 | 主要所有者 |
| --- | --- | --- |
| 普通包 import | caller contracts；不加载 Entari integration、adapter、composition root 或可选原生引擎 | Python import 调用方 |
| `build_runtime_plan()` | selected Provider、parsed config、resource strategy、可选 host transport 对象 | 创建 plan 的宿主 |
| `RuntimePlan.build_runtime()` | 一次性的 `RenderRuntime` 图；可加载配置的 drawing source | runtime |
| `HtmlRenderService` | Entari generation facade、Launart stages 与故障状态 | Entari plugin |
| `DrawingSourceRegistry` | 名称、源码、模块依赖、重载与 lease | drawing registry 与共享 pool |
| Letoderea provider | 从当前 service 解析六个 caller contract | Entari plugin |

## import、plan 与 service

`entari_plugin_htmlrender` 的普通 import 只暴露 caller-facing contracts 和 value objects。没有 Entari 注入的 `__plugin__` 时，package root 不导入 `arclet.entari`、`entari_plugin_htmlrender.composition`、adapter 或可选原生引擎，也不注册 service。

Entari loader 在插件模块的全局命名空间中提供 `__plugin__` 后，package root 才调用 `register_plugin()`。该入口声明 metadata 与 `HtmlRenderConfig`，解析宿主拥有的 Playwright 默认缓存路径，并创建 `RuntimePlan`。

`build_runtime_plan()` 不启动 server、transport 或 HTML 后端，也不获取 runtime resource。它会解析配置所选的单个 Provider，因此可能读取已安装的 entry-point metadata、import 该 Provider 模块并调用 `parse_config()` 与 `resource_strategy()`；Provider 的 availability 与 composition 仍必须遵守无 I/O 契约。

`RuntimePlan` 是 one-shot value，`build_runtime()` 恰好消费一次。runtime construction 会建立 admission、缓存、resource、template、graphics、Provider binding 与可选 filehost 对象；配置了 Python drawing 时，drawing registry 可以在此读取源码摘要、声明模块并加载源码。它仍不会启动 HTML Provider 或监听 host transport。

初次插件加载会在 `register_plugin()` 内同步消费 plan，因此 drawing source 的首次读取、import 和入口校验发生在 plugin load 阶段。disable 后的 successor 则在 Launart `preparing` 阶段才消费自己的新 plan，禁用期间不会为了 successor 预先 import drawing。

`HtmlRenderService` 是这一 generation 的 Entari facade，不是另一个可手工重启的 runtime API。业务代码可以读取 `preparation`、`renderer`、`templates`、`resources`、`graphics`、`drawings` 与 `capabilities`；不要读取内部 runtime，也不要调用 `startup()`、`probe()` 或 `aclose()` 来替代 Launart。

HTML 后端由配置中的 `provider` 选择，而不是由 `rasterize_*()` 的逐次参数选择。修改 Provider、预算、resource 或 drawing 绑定需要 Entari config reload；切换步骤见[多引擎与切换](../guides/switching-engines.md)。

## DI 与当前 generation

插件安装一个 Letoderea provider factory，供 handler 按接口注入以下六个 contract。factory 不保存某个已关闭 generation 的 contract；每次解析都寻找 Launart 当前的 `htmlrender.runtime` component。

| 注入类型 | 当前 generation 的入口 |
| --- | --- |
| `HtmlRenderer` | `service.renderer` |
| `TemplateRenderer` | `service.templates` |
| `HtmlPreparer` | `service.preparation` |
| `ResourceAccess` | `service.resources` |
| `GraphicsRenderer` | `service.graphics` |
| `DrawingRenderer` | `service.drawings` |

`capabilities` 仍可从 concrete `HtmlRenderService` 读取，但它不属于上述六个直接 DI contract。

解析期间，provider 会读取当前插件 module 上的故障状态。service 尚未出现时，若插件仍在 enabled 状态，解析等待当前 service；插件已 disabled 或 unloaded 时立即失败；service 准备失败或清理失败时，解析得到 `RuntimeUnavailableError(state="failed")`，不会无限等待。

atomic reload 后，已编译 handler 使用的 provider 仍应解析新 plugin module 的状态和新的 Launart component。业务代码应持续通过 DI 获取 contract；长期缓存旧 `HtmlRenderService`、facade、capability 或 `DrawingRenderer` 会在 generation 关闭后得到 `RuntimeUnavailableError`。

插件 dispose 时移除自己的 provider factory。不要手工重复安装该 factory，也不要依赖一个全局 singleton 作为当前 generation 的替代品。

## Launart stages

`HtmlRenderService` 声明 `preparing`、`blocking` 与 `cleanup` 三个阶段，不要求其他 component。初次加载已有 plugin-load runtime；successor 若以 `runtime=None` 创建，则在 `preparing` 中先构建自己的 plan 与 runtime。

### preparing

generation 进入 `preparing` 后，若还没有 runtime，service 通过 generation factory 创建 plan、runtime、Provider transport 与 drawing registry。随后先启动 plan 持有的显式 aiohttp filehost，再按 `startup` 策略处理 HTML Provider。

| `startup` | preparing 行为 |
| --- | --- |
| `off` | 不走 eager Provider startup；runtime 仍为 `OPEN`，首个已获准 Provider operation 可以 lazy acquire |
| `warmup` | eager 调用 runtime `startup()` |
| `probe` | eager 调用 runtime `startup()`，随后再执行 Provider `probe()` |

显式 filehost 的启动不受 `startup: off` 影响。`off` 关闭的是 eager Provider startup，不是整个 service、drawing source 或 transport ownership；如果 resource strategy 需要 filehost，它仍会在 preparing 阶段监听。

启动任一步骤失败时，service 先关闭 runtime，再关闭 filehost，并保留 startup error；若 rollback 再失败，则用 exception group 同时保留两类错误。Provider composition 内部的 startup rollback 同样按已完成步骤反向撤销，rollback 失败会 poison 该 composition。

service 捕获 preparing 故障并写入 generation 状态，然后结束 `preparing` context，而不是让 Launart stage 永久悬挂。诊断时应同时查看结构化 startup error、rollback error 与日志中的“reload the plugin to recover”。

### blocking

没有记录故障时，`blocking` 只等待 Launart 的退出信号。它不再启动第二套 runtime，也不负责配置 watcher；配置生效依赖宿主调用 Entari 的 reload 机制。

preparing 已记录故障时，该 generation 跳过 exit 等待并直接进入 cleanup。此行为用于完成 framework stage、唤醒 DI waiter 并允许 Launart 移除 component；它不会把失败 generation 恢复成可用状态。

### cleanup

cleanup 先让 generation runtime 进入 `CLOSING`、永久停止接纳新 operation，并等待已接纳 operation 完成；随后执行 drawing、Provider、template、resource、remote transport 与 publisher 的 best-effort teardown。hosted filehost 只在 runtime drain 完成后关闭，避免仍有 work 使用已发布的 URL。

runtime drain 被取消时保持 `CLOSING`，filehost 继续存活，下一次 cleanup 可以重试。其他 runtime cleanup error 不会阻止 service 尝试关闭 filehost，两个 owner 的错误会聚合报告。

service 在 `_close_lock` 下执行关闭，因此并发 cleanup 只成功关闭一次。只要有 runtime 或 filehost cleanup error，`_closed` 就不会置位；后续 plugin disposal 或 reload 可以再次进入同一关闭边界。

cleanup 失败时 service 仍结束 Launart stage，并把错误写入共享 generation state，避免 disable、enable 或 DI waiter 永久等待。此时 facade 报告 `RuntimeUnavailableError(state="failed")`；显式 reload 才是恢复路径。

## 清理所有权与可重试边界

插件注册了 plugin-level `collect_disposes()` 回调，用于在 staged composition 尚未形成 service，或正常 service cleanup 未完成时再次关闭源码。正常 generation 的清理优先级如下：

1. `HtmlRenderService` 关闭当前 `RenderRuntime`，runtime admission 先停止接纳并排空。
2. composed lifecycle 关闭 drawing registry、Provider、templates、resources、remote transport 与 publisher。
3. service 关闭该 generation 的 hosted filehost。
4. plugin disposal 可再次调用 same-generation close；drawing pool 在最后一个 registry 释放后卸载自己拥有且仍未被引用的 plugin roots。

所有 teardown 步骤尽量都执行，不会因为前一个 owner 失败而跳过剩余 owner。多个失败以 `ExceptionGroup` 保留；单步失败保留原异常。retry 会重新进入相同 generation 的关闭边界，已经完成的幂等 owner 不应重复创建资源。

cleanup 成功后，普通 disable 才可能登记 successor；unload、atomic reload 和 Launart 正在退出时都不会登记。cleanup 失败时没有 successor，failed generation 也不会因为再次 enable 而变得可复用。

## disable 与 enable

```text
A blocking
  -> disable
  -> cleanup A
       fails: A remains failed; no successor; reload required
       succeeds: enqueue lazy A'
  -> enable
  -> Launart preparing builds new runtime graph A'
  -> A' blocking
  -> disable
  -> cleanup A'
```

只有在旧 generation 完整 cleanup 成功、owner 仍可用、Launart 处于 `blocking` 且未退出时，service 才把后继登记到同一 owner。后继保留创建时复制的配置，并以 `runtime=None` 等到下一次 enable 的 `preparing` 再构建。

每次 disable/enable 成功循环都会产生新的 runtime generation；旧 facade 与 capability 保持关闭，新的 contract 必须经 DI 获取。disable/enable 只重启，不重新读取磁盘配置，也不改变 `provider`、bootstrap 或 drawing 绑定。

若 cleanup 或 successor startup 失败，不要继续复用该 service 或反复 enable 期待自动修复。通过 Entari 显式 reload 插件，让 staged import、旧 owner 清理和新 generation 重新执行。

## staged reload 的两个事务

> [!IMPORTANT]
> 新插件完成 promote 之前，导入失败可保留旧插件；promote 之后启动或探测失败，需要显式重载恢复，不会自动回滚到旧服务。

```text
A blocking
  -> stage A*
       Python import
       metadata + HtmlRenderConfig validation
       provider resolution + parse + resource strategy
       runtime graph + availability/composition
       configured drawing load + entry validation
       failure here: discard A*; restore old module entries; A stays active
  -> dispose A
  -> promote A*
  -> A*.preparing: filehost + runtime startup/probe
       failure here: A* is promoted and failed; A is not restored
  -> A* blocking
```

HTMLRender 的配置校验、plan 创建与 runtime construction 发生在 plugin import 内，因此属于 pre-promote staged transaction。新模块的 Python import、metadata/config 校验、Provider discovery/config/strategy、runtime 图构建、availability/composition、drawing source 加载与入口校验若失败，Entari 丢弃 staged tree，恢复旧模块登记，`reload_plugin()` 返回失败。

staged 成功后再处置旧 owner 并 promote 新插件。旧 service 在 replace 清理中排空并关闭，旧 drawing registry 释放它的源码引用；新 runtime 在重叠期间保留同一 drawing pool 中仍需要的使用记录。

promote 完成后，新 service 才进入 Launart startup/probe。filehost bind、Provider eager startup 或 readiness probe 在这里失败时，旧插件已经不存在；service 记录失败、结束 stages 并等待显式 reload。`startup: off` 能避免 eager Provider startup，却也意味着该阶段问题可能推迟到首个 lazy operation，不能把它当作部署验证的替代。

`startup: probe` 只能在 promote 后证明启动/探测结果。若部署需要在上线前阻止 post-promote 失败，应在隔离环境使用同一配置执行启动检查，再应用配置；当前实现不会为 post-promote 故障执行跨 generation 的事务回滚。

htmlrender 的 config reload 与 drawing 的 `reload: true` 是不同事务。前者重建 service generation；后者只在下一次对应 drawing call 或显式 `drawings.reload(name)` 时检查源码，不重建 HTML Provider，也不会让应用开始持续监视文件。

## drawing canonical module

配置的 `path` 或 `module` 会解析成真实、可 import 的 Python 模块名。同一个源码文件必须以唯一 canonical name 出现；两个配置指向同一文件但通过冲突名称解析，会在 import 前被拒绝。

registry 先用 `PathFinder`/module spec 定位源码，读取入口文件摘要，再把真实包中的 helper 名称通过 Entari `requires()` 声明为独立 plugin。发现与声明 helper 不会执行尚未 import 的文件；只有实际 import 可达的 helper 才会运行模块体。

源码不是已加载的 Entari plugin 时，registry 通过 `load_plugin()` 导入 canonical module。源码已被其他 Entari plugin 以同一文件加载时可以借用；如果源码已由普通 Python import 加载但不是 Entari plugin，配置会被拒绝，避免把未托管的模块冒充为可重载插件。

多个 drawing imports 同一个 helper 时共享一个 canonical module。互相 import 的 drawing 也共享当前 generation 的模块身份；路径别名、模块别名和父包属性由 registry 与 Entari binding index 维护。

`reload: true` 要求依赖关系可被 Entari 识别，并拒绝在首次 import 中已经变成 subplugin 的 helper 结构。共享代码应使用真实 package、明确模块路径的 `import` 或 `from ... import name`，并按[绘图后端配置](../configuration/graphics/index.md)组织 lazy helper import。

## drawing reload 与失败边界

| 触发 | 检查时机 | 发生的替换 |
| --- | --- | --- |
| `reload: true` 的 drawing call | 每次对应 `render(name, ...)` 前 | 摘要变化时 topologically reload 已登记依赖 |
| `await drawings.reload(name)` | 显式调用时 | 即使配置为 `reload: false` 也强制检查并重载 |
| 配置变更后的 Entari reload | 宿主实际执行 config reload 时 | 重建 HTMLRender generation 与 drawing registry |
| `::auto_reload` 等外部 Entari reload | 该外部机制触发时 | 当前 registry 下次 lease 读取当前 plugin callback |

`reload: false` 不执行逐次源码摘要检查，但每次 lease 前仍会声明包内新出现的模块名；它不会 eager import 尚未被引用的 helper。其他 drawing 触发的依赖 reload 或外部 Entari reload 更新 canonical module 后，该 drawing 下次仍从当前 plugin 读取入口，因此不会冻结在旧 callback。

真正发生源码变化时，registry 在工作执行器计算摘要，并按依赖顺序调用 `reload_plugin()` 或 `reload_subplugin()`。Python syntax/import 失败时，Entari staged reload 保留旧 module；自动检查记录失败摘要并继续当前可用入口，显式 `drawings.reload()` 则把 `DrawingLoadError` 抛给调用方。

模块成功 reload 后，新模块的入口校验或后续 `draw()` 执行仍可能失败。实现不会因为入口无效、异步 `draw()` 被误配置为同步入口或绘图函数抛错而恢复旧 callback；这是需要与 import failure 分开处理的故障面。

Entari 的模块重载不是整张依赖图的事务回滚。顶层初始化、模块副作用或依赖方的 callback 校验失败可能留下已完成的部分替换；维护者应让共享模块初始化可重复、可观察，并避免在 import 时执行外部工作。

`reload: true` 本身不是 filesystem watcher。没有对应 drawing call 或显式 reload 时，源码变化可以一直未被发现；需要后台文件事件时，应由宿主的 Entari auto-reload 机制单独提供。

## drawing leases 与跨 generation 引用

`DrawingService.render()` 在分配画布前进入 runtime admission；`DrawingRenderer.reload()` 使用同一 admission gate 的单独 operation。关闭开始后，这两个入口都拒绝新工作，已接纳 operation 才进入 drain 等待。

registry `lease(name)` 在 pool lock 内完成可选源码刷新、canonical plugin 可用性检查与 callback 获取，然后增加 active lease。native drawing 执行结束后，lease 的 `finally` 记录本次实际加载的 plugin roots、减少 active 数，并在最后一个 lease 结束时唤醒 cleanup。

drawing close 先标记 registry closing 并拒绝新 lease，再在 shield 中等待 active leases。等待结束后 pool 才解除该 registry 的 roots 与 plugin references；取消关闭不会让尚未完成的 callback 失去模块。

atomic config reload 可以短暂出现两个 registry。新 registry 复用仍由旧 registry 或外部 plugin 使用的 canonical modules；旧 registry 关闭时只移除自己的 reference。pool 仅在 module 没有本 pool user、也没有外部 plugin dependents 时卸载自己创建的 root。

原有外部 plugin 与 borrowed source 不会被 pool 接管。即使 drawing 配置被移除，其他 plugin 仍引用的源码和必要的 `sys.path` mount 也会保留，直到引用消失。

## 维护者检查清单

- 普通 import 不执行 host registration、adapter startup、网络或原生 runtime acquisition。
- Provider discovery import 保持轻量；availability、resource strategy 与 composition 不获取 runtime resource。
- HTML Provider 的启动和 runtime resource acquisition 只发生在新 generation 的 Launart stage 或已获准的 lazy operation；绘图源码的 import 可在 plugin load 阶段发生，模块体应避免外部 I/O。
- 每个 generation 使用自己的 admission、runtime、Provider transport、cache 与 filehost；不要跨 generation 复用 caller contract。
- cleanup 先停止接纳并 drain，再关闭依赖该 admission 的资源；保留取消与失败的可重试状态。
- staged 失败路径只在 promote 前保证旧插件继续运行；promote 后的 startup failure 必须显式 reload 恢复。
- config reload、drawing source reload 与外部 auto-reload 使用不同触发条件；文档不得把 `reload: true` 描述成后台 watcher。
- drawing canonical module 的唯一性、依赖声明与 lease drain 必须一起成立，不能只验证入口函数是否可调用。
