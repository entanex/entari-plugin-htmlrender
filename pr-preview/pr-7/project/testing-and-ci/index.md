# 测试矩阵与 CI 流水线

仓库把测试按运行代价分为三层，既保证日常开发反馈迅速，也在 CI 中覆盖多版本 Python、多平台与真实浏览器环境。

## 测试分层

| 测试档位 | 触发命令 | 说明 |
| --- | --- | --- |
| **CI 单元测试** | `make test` | 设置 `HTMLRENDER_TEST_PROFILE=ci`，通过 `pytest-xdist` 并行执行，跳过 `requires_browser` 标记用例，强制检查覆盖率 `>= 90%` |
| **本地浏览器测试** | `make install-browser` 后执行 `make test-local` | 设置 `HTMLRENDER_TEST_PROFILE=local`，串行执行并运行真实 Chromium 浏览器用例（使用 `.artifacts/playwright-browsers`） |
| **远程浏览器冒烟** | `make remote-smoke` / `make remote-smoke-build` | 通过 Docker Compose 启动独立 Playwright Server 容器与渲染端容器，验证真实跨容器通信（清理使用 `make remote-smoke-down`） |

## 5 项必过状态检查（`main` 分支）

任何 PR 合并到 `main` 前，以下 5 项检查必须全部通过：

1. **`Required Checks`**（`ci.yml`）：Ruff 格式与 Lint、Ty、Basedpyright（含公开类型完整性）、构建包校验、Python 3.11 / 3.13 / 3.14 隔离安装 Wheel 冒烟、Docker 远程浏览器冒烟以及 Entari 插件加载测试。
2. **`Coverage Matrix`**（`coverage.yml`）：在 Python 3.11–3.14 × `x64` / `arm64` 矩阵上运行测试，每个单元格覆盖率均需 `>= 90%`。
3. **`Entari Compatibility Matrix`**（`entari-compat.yml`）：验证与目标 Entari 版本的隔离安装兼容性、Checker 测试与严格真实 Chromium 测试。
4. **`Prek`**（`prek.yml`）：运行仓库配置的全部预提交质量检查。
5. **`Docs Preview`**（`docs-pr-preview.yml`）：以严格模式构建 Zensical 文档站点，确保无断链、无无效锚点。

## 其他 GitHub Actions 工作流

| 工作流文件 | 触发方式与用途 |
| --- | --- |
| `docs.yml` | 推送 `main` 时执行严格模式文档构建校验 |
| `docs-pr-preview*.yml` | 三段式 Fork 安全预览流：构建制品 → 通过 `workflow_run` 部署到 `gh-pages/pr-preview/pr-N/` → PR 关闭后自动清理 |
| `auto-tag.yml` | `main` 上版本号变更且 5 项必过工作流全部通过后，自动打不可变 annotated tag 并触发发布 |
| `publish.yml` | 校验 tag/SHA/版本一致性，通过 OIDC 可信发布上传 PyPI、创建 GitHub Release 并部署版本化文档 |
| `publish-test.yml` | 仅支持手动触发，用于上传构建产物到 TestPyPI 预演 |

> [!NOTE]
>
> **供应链安全约束**
>
> 仓库所有 GitHub Actions 均固定到完整的 commit SHA，CI 中的 `uv` 版本也固定（如 `uv==0.11.28`）。
