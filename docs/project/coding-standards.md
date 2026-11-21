---
title: 编码规范
description: Python、异步模型、测试与可观测性的协作规范
icon: lucide/code-2
status: new
tags:
  - Project
  - Standards
---

# 编码规范

## 总则

1. 优先保证行为正确与可回归验证。
2. 优先写“可读、可测、可维护”的代码。
3. API 兼容性变化必须有明确影响说明。
4. 当局部规则冲突时，优先保持同一文件/模块的一致性。
5. 不通过 `type: ignore`、全局 lint 排除或吞掉异常来隐藏本次变更引入的诊断。

## 目录与文件组织

- 目录按依赖层组织（`runtime` / `rendering` / `preparation` / `resources` / `adapters` / `entari`），避免按“代码类型”堆目录；
- 文件尽量保持“单一概念”，避免一个文件同时承担多个无关职责；
- 测试目录按插件实现分类维护，不把浏览器相关 case 统一堆放。

## Python 与工具链

- Python 版本与依赖以 `pyproject.toml` 为准。
- 支持版本：Python 3.11–3.14。
- 格式化：`ruff format`；CI 使用 `ruff format --check` 验证，不修改工作区。
- Lint：`ruff check`
- 类型检查：`basedpyright` + `ty`，并对 `py.typed` 公共面运行 package verifytypes
- 测试：`pytest` + `pytest-cov`

提交前至少通过：

```bash
make ruff-format
make ruff-format-check
make ruff-check
make typecheck
make ty
make test-ci
```

- 新代码使用当前仓库的类型表达方式，不为某一个检查器制造专用的公开 API。
- `ruff format` 与自动修复只用于生成有意提交的变更；合并门禁必须使用非修改模式。
- 更新依赖时通过 `uv` 修改项目元数据并刷新 `uv.lock`，保持 `uv sync --locked` 可重现。

## 异步与并发规范

- 上层协作语义使用 `anyio`；
- 对 Playwright/subprocess 这类 asyncio 原生能力，允许在实现层保持兼容调用；
- 避免模块级全局状态竞争，涉及共享状态需显式加锁；
- 并发路径必须有测试覆盖（成功、失败、超时、取消）。

## Runtime 与 Provider 规范

- 跨引擎能力先进入 request/use-case/port；专属能力通过 typed Capability 暴露；
- 核心层不依赖具体 Provider adapter；
- Provider 与资源服务只通过 composition 注入依赖，不读取全局配置；
- 资源策略变更需同步更新使用指南、配置文档与兼容性说明。

## 日志与可观测性规范

- 错误日志必须包含上下文（操作名、Provider ID、稳定错误类别）；
- Sentry/Prometheus 为可选能力，缺失时应有本地可观测回退（如 debug 日志）；
- 避免在高频路径打无意义 debug，必要时加开关或采样。

## 测试规范

- 按实现模块组织测试，不按“工具类别”堆叠；
- 需要真实浏览器的测试使用 `@pytest.mark.requires_browser`；
- 非浏览器单元测试默认应可在 CI profile 运行；
- 并发与生命周期测试必须覆盖“资源释放”路径；
- bugfix 先提供能在修复前失败的回归测试；新 Provider 同时覆盖 SDK、通用 executor 与 typed Capability；
- 不依赖测试执行顺序、共享进程全局状态或外部网络；确需外部服务的 case 放入明确的 smoke 层；
- 插件入口、元数据或依赖变化必须通过 Python 3.11–3.14 的 Entari 加载矩阵。

## 验证分层

| 层级 | 必须验证的行为 | 典型入口 |
| --- | --- | --- |
| 仓库级 hooks | 冲突、文件格式、元数据、拼写、源码与文档修复器 | `prek run --all-files` |
| 静态质量 | Ruff format/check、`basedpyright`、`ty` | `make ruff-format-check ruff-check typecheck ty` |
| 单元与集成 | 非浏览器 pytest；CI 额外采集 coverage | `make test-ci` / CI `Coverage` |
| 插件加载 | 隔离安装、Entari import/load、元数据与配置 | CI Entari load matrix |
| 分发包 | wheel + sdist 可构建，metadata 可被 pinned `twine` 解析 | `make build-artifacts` |
| 文档 | 链接、引用与配置通过 strict build | `make docs-build` |
| 本地浏览器 | 需要 Chromium 的 Playwright 行为 | `make install-browser && make test-local` |
| 远程浏览器 | Docker 多容器、WebSocket 与资源可达性 | `make remote-smoke` |

浏览器和 Docker smoke 是条件门禁：只要改动触及页面生命周期、Playwright transport、资源解析、Filehost、模板注入或容器配置，就应运行对应层，而不是仅凭单元测试判断。

`prek` 与静态质量不是重复门禁：前者还覆盖 YAML、Markdown、拼写、冲突标记、项目元数据与 workflow，并可能执行自动修复；后者完整检查 Python 类型和测试行为。修改 workflow 时还需运行 manual `actionlint`，完整命令与重跑规则见[工程协作流程](engineering-workflow.md#prek-gates)。

## 文档同步规范

以下变更必须同步文档：

- 对外 API 行为变更
- 配置项新增/重命名/弃用
- 架构分层或生命周期变更
- CI/CD 策略调整
- 发布、版本或包元数据策略调整

按信息职责更新唯一 canonical 页面：

- `docs/start/`：首次接入与 Provider 选择；
- `docs/guides/`：完成具体任务的操作步骤；
- `docs/configuration/`：配置字段、部署、安全与排障；
- `docs/extensions/`：架构、Provider SDK 与资源管线；
- `docs/reference/`：统一术语、公共 API、类型、生命周期与错误契约；
- `docs/project/`：协作、测试、治理与发布。

站点导航不直接复制物理目录：它按读者任务组织为“开始使用、使用指南、配置与部署、API 参考、扩展开发、维护者指南”六个顶层章节。`configuration/` 统一承载字段、部署、安全与排障；`reference/` 只描述稳定调用契约。一个 canonical 页面只能在导航中出现一次。

各章按下面的阅读顺序组织，入口页中的分组和链接顺序与侧栏一致：

| 章节 | 排列顺序 |
| --- | --- |
| 开始使用 | 快速开始、选择 Provider、版本升级 |
| 使用指南 | 内容渲染、Python 与场景绘图、组合与集成 |
| 配置与部署 | 基础配置、HTML Provider、绘图后端、资源与预算、诊断与排障 |
| API 参考 | Runtime、Preparation 与资源、渲染、Capability、术语 |
| 扩展开发 | 运行机制、Provider 开发 |
| 维护者指南 | 贡献与设计、检查与提交、发布与维护 |

章节内至多增加一层主题分组，分组至少包含两页；简短章节直接列出页面。HTML Provider 中先列 Takumi，再列 Playwright 与远程连接；插件启动配置归“配置与部署”，所有权、DI 与重载事务归“扩展开发”。缓存页面保留 `guides/cache-lifecycle.md` 地址，导航归“资源与预算”。新增或移动导航项时，同步入口页与 `llmstxt.sections` 的章节归属和顺序。

项目从 `0.1.0` 开始，不维护旧文档目录或重定向页面。页面确需改名时，先判断已发布 URL 的兼容责任，再设计重定向与删除周期。

### 标题与图标

- 每页保留一个主标题，通常由 Markdown `#` 提供；定制首页可以使用语义等价的 HTML `<h1>`。`title` 与正文主标题使用相同名称，导航允许使用不改变含义的简短名称。
- `##` 表示主题，`###` 只用于该主题下需要独立定位的子项，不跳级，也不为了缩小字号增加标题层级。强调一句结论时使用正文或提示框。
- 所有页面都配置 `title`、`description` 和一个 `icon`，按此顺序书写。页面图标统一选用 `lucide/`，按任务含义选择；侧栏的页面链接显示图标，分组标题统一只显示文字，不在标题里重复添加 emoji。
- 六个顶层章节保持稳定；导航分组用于区分任务或职责，不机械复制目录结构。章节索引的后续入口统一使用“下一步”。
- 标题或页面名称变更前检索入站链接，保留需要兼容的锚点，并通过 strict build 检查导航与链接。

### 主题与颜色

文档主色取自 [Arclet 文档](https://arclet.top/) 的 `--vp-c-brand-*`，集中定义在 `docs/stylesheets/extra.css`；`mkdocs.yml` 使用 `primary: custom` 和 `accent: custom`，不再叠加预设颜色。

| 用途 | 浅色模式 | 深色模式 |
| --- | --- | --- |
| 主色 | `#3451B2` | `#0178FF` |
| 次级品牌色 | `#3A5CCC` | `#6780E6` |
| 按钮基色 | `#5672CD` | `#4552E6` |

深色模式中的正文链接使用次级品牌色；主按钮背景在基色上略微加深，以保持文字对比度。背景和正文颜色沿用当前主题变量，首页同样跟随明暗模式；不得用固定深色背景覆盖浅色正文。语义提示保留各自的警告、错误和成功颜色，不全部改成品牌色。

样式变更后检查首页、长正文与分组侧栏的桌面/手机布局，核对键盘焦点、标题定位、图标对齐和明暗模式对比度。首页保留完整的 CSS 动画，包括流线、光点与预览卡片，不按 `prefers-reduced-motion` 自动关闭或削减；装饰层限定在首页主视觉内，不占用正文的滚动或点击区域。首页仅保留简短介绍、操作入口与 Takumi 横幅，配置说明、弃用计划和章节索引放在对应文档页。

### 文档表达层级

具体语法以 [Zensical Authoring](https://zensical.org/docs/authoring/markdown/) 为准。Zensical 组件用于表达语义，不用于装饰页面：

- admonition 放置不应打断主叙事、但不能被忽略的提示、约束或风险；标题必须直接说明结论，避免只有“注意”或“提示”；
- collapsible details 收纳按症状展开的排障、兼容背景和其他可选细节，不隐藏完成当前任务必需的步骤；
- content tabs 只组织互斥实现、环境或协议；有先后关系的步骤继续使用有序列表；
- data table 表达字段映射、精确对比和测试矩阵，card grid 只用于入口页或同级导航；
- code annotations 把解释贴到配置或代码的对应行，不重复解释整个代码块；
- Mermaid 表达跨越至少三个参与者的依赖、流程或生命周期，不替代简单列表；浏览器runtime 必须使用仓库自托管的固定版本，不依赖构建或阅读时访问外部 CDN；
- button 只标记页面的主要行动入口；footnote 与 tooltip 只承载不影响主结论的出处、缩写和补充定义。

任何新增组件都必须在窄屏下保持主叙事顺序，并通过 `make docs-build` 的 strict链接、anchor、引用和配置验证。

当前 Mermaid runtime 固定为 `11.16.0`，来自 npm 发布包的`dist/mermaid.min.js`；原始 MIT 许可证位于[`docs/assets/licenses/mermaid-11.16.0.txt`](../assets/licenses/mermaid-11.16.0.txt)。升级时使用 `npm pack mermaid@<version>` 提取发布产物，同时更新文件名、配置引用与许可证；不得改回 `mermaid@11` 这类 moving
major CDN URL。
