# 参与贡献与本地开发

欢迎为 `entari-plugin-htmlrender` 提交 Issue 与 Pull Request！本页汇总本地开发环境搭建、代码质量规范与提交流程。

## 快速搭建本地环境

项目使用 `uv` 管理 Python 依赖（支持 Python **3.11–3.14**，开发锁定的 Entari 版本为 `0.19.4`）：

```bash
# 同步全部可选依赖与开发工具，并安装 prek git hooks
make prepare
```

## 常用开发命令

| 命令 | 作用 |
| --- | --- |
| `make check` | 一键执行格式检查、Ruff Lint、Basedpyright（含公共类型完整性）、Ty 与 CI 单元测试 |
| `make ruff-format` | 使用 Ruff 自动格式化代码 |
| `make test` | 并行运行 CI 测试集（跳过真实浏览器用例，要求覆盖率 \>= 90%） |
| `make install-browser` | 安装项目本地隔离的 Playwright Chromium（存放于 `.artifacts/playwright-browsers`） |
| `make test-local` | 串行运行包含真实浏览器的本地测试 |
| `make remote-smoke` | 通过 Docker Compose 运行远程 Playwright 冒烟测试 |
| `make docs-serve` | 本地启动文档预览服务器 |
| `make docs-build` | 以严格模式构建文档站点（`zensical build --strict`） |

## 编码与架构规范

1. **格式与静态检查**：所有改动必须通过 `ruff format --check`、`ruff check`、`basedpyright`（以 Python 3.11 为目标，且公开 API 需满足 **100% 类型完整性** `basedpyright --verifytypes entari_plugin_htmlrender --ignoreexternal`）以及 `ty check`。
2. **核心层解耦**：`rendering`、`preparation`、`resources`、`graphics`、`runtime` 五个核心包禁止导入 `adapters`、`composition` 或 `entari`。所有可选依赖组（包括 `[all]`）均不得引入 NoneBot。
3. **异步与状态管理**：上层异步代码统一使用 `anyio`；禁止在模块顶层存放全局可变运行状态。
4. **测试覆盖率**：每个测试矩阵单元的代码覆盖率不得低于 **90%**。
5. **Prek 钩子**：提交前可运行 `prek run --all-files` 检查；如果修改了 `.github/workflows/`，还需运行 `prek run actionlint --all-files --hook-stage=manual`。

## 提交消息规范（Conventional Commits）

仓库使用 Angular 风格的提交规范，并由 `commit-msg` git hook 自动校验：

```text
<type>(<scope>): <subject>
```

- **允许的 `type`**：`feat`、`fix`、`docs`、`refactor`、`perf`、`test`、`build`、`ci`、`chore`、`revert`。
- **`subject` 要求**：使用祈使语气、小写开头、不超过 72 个字符、末尾不加句号。
- **破坏性变更**：在 `type` 或 `(scope)` 后加 `!`，或在正文底部添加 `BREAKING CHANGE:` 说明。

## Pull Request 流程

- 从 `main` 切出短期功能分支进行开发。
- **仅使用 Squash Merge 合并**：PR 标题将直接作为合并后的最终提交消息，请确保 PR 标题同样符合 Conventional Commits 规范。
- 合并前需满足：分支已同步最新 `main`、至少 1 位非作者维护者批准（新推送会重置旧批准）、所有 Review 评论已解决，且 5 项必过 CI 检查全部通过。合并后自动删除源分支。
