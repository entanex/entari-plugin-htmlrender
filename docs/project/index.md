---
title: 维护者指南
description: 贡献流程、质量门禁、GitHub 自动化、仓库治理与发布职责
icon: lucide/construction
---

# 维护者指南

本章描述仓库协作和发布职责；运行时设计与第三方扩展统一放在[扩展开发](../extensions/index.md)。普通插件调用方不需要阅读本章。

## 贡献流程

1. [贡献指南](contributing.md)
2. [工程协作流程](engineering-workflow.md)
3. [编码规范](coding-standards.md)
4. [提交消息指南](commit-messages.md)
5. [Pull Request 生命周期](pull-requests.md)

## 质量与发布

- [测试矩阵](testing.md)
- [CI Actions](ci.md)
- [仓库治理与保护](governance.md)
- [发布流程](release.md)
- [文档版本管理](documentation-versioning.md)

## 本地入口

```bash
make prepare
make check
make docs-build
```

涉及浏览器行为时增加 `make test-local`；涉及远程连接或资源 transport 时增加`make remote-smoke-build`。

## 下一步

首次贡献从[贡献指南](contributing.md)开始；维护工作流时同时核对[CI Actions](ci.md)与[仓库治理](governance.md)；准备发行时按[发布流程](release.md)逐项执行。
