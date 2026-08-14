---
title: 扩展开发
description: 实现第三方 Provider，并理解其依赖的架构与资源契约
icon: lucide/blocks
---

# 扩展开发

本章面向第三方 Provider 作者和核心实现维护者。应用调用方通常只需要[使用指南](../guides/index.md)和[API 参考](../reference/index.md)。

本区解释概念之间的关系，不重复定义名词；定义统一收录在[术语表](../reference/glossary.md)。

## 实现 Provider

1. [Provider 契约](provider-contract.md)：确认 discovery、config、binding 与 capability 约束。
2. [Provider 开发指南](provider-development.md)：实现、测试并发布第三方 Provider。

## 理解实现边界

1. [分层架构](architecture.md)：理解 application、preparation、resource 与 adapter 边界。
2. [资源管线](resource-pipeline.md)：深入授权、缓存、物化与远程传输不变量。

第三方 Provider 对外只依赖公开 SDK；不要导入 Entari integration、内部 composition实现或具体 `ResourceService`。

## 下一步

完成实现后按[测试矩阵](../project/testing.md)验证，并遵循[语义 API 设计](../project/semantic-api.md)检查公开词汇。
