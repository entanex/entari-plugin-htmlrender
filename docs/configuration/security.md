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
- 文件系统模板会在每次读取前校验解析符号链接后的实际文件，包含 `include`、`extends` 与 `import`；可重载模板的缓存也会重新校验链接目标。
- 不把调用方输入直接拼接为模板名或本地路径。

## 网络

- 默认拒绝非公网解析地址。访问回环、RFC 1918、链路本地、CGNAT/shared `100.64.0.0/10`、ULA 等地址时，必须把目标 IPv4/IPv6 地址或 CIDR 显式加入 `resources.remote_access.allow_private_networks`。
- `allow_hosts: []` 不限制主机名，但仍受 IP 策略约束；非空列表只允许列出的主机及其子域。`allow_hosts` 不能绕过 IP 白名单，`deny_hosts` 始终优先。
- `allow_private_networks` 只接受 IP/CIDR 列表，默认 `[]`；旧版布尔值 `true` / `false` 无效。
- 限制 redirect、timeout、并发与单资源大小。
- DNS、redirect 与最终连接地址均需保持在策略内；部署层同时限制 egress。
- 受管理的 Playwright HTML rendering 只把 HTTP(S) `GET` 请求交给 Bot-side 的同一资源策略和 pinned transport；WebSocket、非 `GET` 请求和 service worker 会被拒绝。发布请求头仅绑定原 URL，跨 URL redirect 时不会保留，且不会进入授权缓存。这项保护只覆盖 HTTP(S) 资源访问，不构成完整 Chromium sandbox。显式 `lease_page()` / `lease_browser()` 返回调用方持有的原生对象，其导航与后续请求仍由调用层校验。

## 升级迁移

旧配置中的 `allow_private_networks: true` 或 `false` 会被拒绝，因为两者都无法表达目标网段白名单。先确认实际依赖的公网与非公网地址，再用 IP/CIDR 列表替换布尔值。旧版通过 `allow_hosts` 绕过私网检查的配置必须同时补充精确的 IP/CIDR；只保留主机名会继续拒绝非公网解析地址。

## 资源发布

filehost 的 `public_base_url` 是显式部署配置，不能由请求 header 推导。`PublishedResource` 原子携带 URL 与精确请求头，二者只在 publication lease 内有效；不得把授权复用到同 host 的其他路径。

## 预算与日志

设置 `html.max_source_bytes`、`max_pixels`、`max_output_bytes`、并发与调用 timeout。日志不要输出完整 `provider_config`、HTML、模板变量、filehost guard 或远程 token；稳定错误的 cause snapshot 仍需在进入外部日志前脱敏。
