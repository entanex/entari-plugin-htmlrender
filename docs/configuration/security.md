---
title: 安全须知
description: 本地文件、远程资源、浏览器导航与输出预算的信任边界
---

# 安全须知

htmlrender 会处理不可信 HTML、模板变量、文件路径和 URL。安全策略应在调用入口、资源服务与部署网络三层同时成立。

## 本地文件

- 保持 `resources.local_access.allow_any_path: false`。
- `allowed_paths` 只加入业务所需的最小只读目录。
- `template_base` 只定位相对路径，不授予目录权限。
- 不把调用方输入直接拼接为模板名或本地路径。

## 网络

- 默认拒绝私网地址；按业务建立 `allow_hosts`，必要时叠加 `deny_hosts`。
- 限制 redirect、timeout、并发与单资源大小。
- DNS、redirect 与最终连接地址均需保持在策略内；部署层同时限制 egress。
- Playwright `Page.goto()` 是原生导航能力，不受 `ResourcePolicy` 保护；导航 URL必须由调用层单独校验。

## 资源发布

filehost 的 `public_base_url` 是显式部署配置，不能由请求 header 推导。授权 header仅用于 `ResourceResolution` 中匹配的精确 URL，不得复用到同 host 的其他路径。

## 预算与日志

设置 `html.max_source_bytes`、`max_pixels`、`max_output_bytes`、并发与调用 timeout。日志不要输出完整 `provider_config`、HTML、模板变量、filehost guard 或远程 token；稳定错误的 cause snapshot 仍需在进入外部日志前脱敏。
