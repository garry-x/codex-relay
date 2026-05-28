# codex-relay 架构与原理

## 概述

codex-relay 是一个 Node.js 包装器，解决廉价 HTTP 代理（如 proxy-cheap）无法正常用于 OpenAI Codex CLI 的问题。

## 问题背景

廉价的 HTTP 代理服务通常存在两个限制：

1. **DNS 过滤** — 代理服务器拒绝解析 `api.openai.com`、`chatgpt.com` 等 OpenAI 域名
2. **TLS 阻断** — 部分代理 IP 被 OpenAI/Cloudflare 边缘节点在 TLS 握手阶段拒绝

codex-relay 通过本地 DNS 解析 + IP 改写解决第一个问题，第二个问题是代理 IP 信誉的固有限制（非 codex-relay 可控）。

## 架构

```
┌─────────┐   HTTP_PROXY   ┌──────────────┐   CONNECT <IP>:443   ┌──────────┐   TCP   ┌──────────┐
│  Codex  │ ──────────────→ │ codex-relay  │ ────────────────────→ │  上游代理  │ ──────→ │ OpenAI   │
│   CLI   │  127.0.0.1:PORT │  local proxy │   Proxy-Auth 注入     │ (proxy)   │         │ Servers  │
└─────────┘                 └──────────────┘                       └──────────┘         └──────────┘
                                  │  ↑
                                  │  │ 1. 本地 DNS 解析
                                  │  │    api.openai.com → 172.66.0.243
                                  │  │
                                  │  │ 2. DNS 缓存 (5分钟自动刷新)
                                  ▼  │
                            ┌──────────┐
                            │ DNS Cache │
                            │ ~/.codex-relay/dns.json
                            └──────────┘
```

### 本地代理工作流程

1. Codex CLI 通过 `HTTP_PROXY=http://127.0.0.1:PORT` 连接到本地代理
2. 本地代理收到 `CONNECT api.openai.com:443`
3. 从本地 DNS 缓存查询 `api.openai.com` → `172.66.0.243`
4. 连接上游代理，发送 `CONNECT 172.66.0.243:443`（用 IP 绕过上游 DNS 过滤）
5. 自动注入 `Proxy-Authorization: Basic ...`（上游代理凭证）
6. 隧道建立后透明转发 TCP 流量

## 组件

### 本地代理守护进程 (codex-relay-proxy)

- 普通用户进程，监听 `127.0.0.1:随机高端口`
- 处理 HTTP CONNECT 和普通 HTTP 请求
- 本地 DNS 解析 + IP 改写 + Proxy-Auth 注入
- DNS 缓存每 5 分钟自动刷新

### DNS 缓存

```json
{
  "api.openai.com": {"ip": "172.66.0.243", "ts": 1748310400000},
  "auth.openai.com": {"ip": "172.64.146.15", "ts": 1748310400000},
  "chatgpt.com": {"ip": "172.64.155.209", "ts": 1748310400000}
}
```

### 配置文件

```
~/.codex-relay/
├── config.json      # 上游代理配置
├── dns.json         # DNS 解析缓存
├── proxy.pid        # 本地代理 PID
├── proxy.port       # 本地代理端口
├── bypass.pid       # bypass PID (root)
└── bypass.error     # bypass 错误日志
```

## 命令速查

```bash
# 配置上游代理
codex-relay proxy set http://user:pass@host:port

# 启动全部服务（本地代理 + bypass）
codex-relay proxy start

# 检查系统状态
codex-relay proxy check

# 测试连通性
codex-relay proxy test

# 预解析 DNS
codex-relay dns cache

# 安装 / 更新
codex-relay install --force

# 运行 Codex
codex-relay run

# 停止全部服务
codex-relay proxy stop

# 清理配置
codex-relay proxy unset
```

## 故障排查

### MCP codex_apps 启动失败

```
⚠ MCP client for `codex_apps` failed to start: MCP startup failed:
  handshaking with MCP server failed: Send message error Transport
  error: Client error: HTTP request failed: http/request failed:
  error sending request for url (https://chatgpt.com/backend-api/wham/apps)
```

#### 背景

`codex_apps` 是 Codex **插件市场（Plugin Marketplace）** 的 MCP 运行时桥接服务。Codex v0.117 引入了插件系统，支持第三方集成（Slack、Figma、Notion、Gmail 等）。`codex_apps` MCP server 负责：

- 连接 `https://chatgpt.com/backend-api/wham/apps` 同步远程插件目录
- 管理插件发现、安装、OAuth 认证
- 为插件提供运行时 MCP 工具调用

对应的 feature flag 为 `apps`（`codex features list` 可查看）。

#### 故障链路

```
codex_apps MCP server (Rust binary, rmcp + reqwest)
  → 直连 chatgpt.com:443
  → /etc/hosts 重定向到 127.0.0.1:443 (bypass daemon)
  → TCP 转发到本地代理 (127.0.0.1:PORT)
  → 本地 DNS 解析 chatgpt.com → Cloudflare IP
  → CONNECT <IP>:443 发送到上游代理
  → 隧道建立 (HTTP 200)
  → TLS ClientHello 发送
  → SSL_ERROR_SYSCALL / tls handshake eof
  → 失败
```

#### 根因分析

**两层问题叠加：**

1. **代理环境变量被忽略**（第一层）

   `codex_apps` 使用的 `codex-rmcp-client` crate 底层依赖 `reqwest`。其 `Cargo.toml` 仅启用了 `json`、`stream`、`rustls-tls` 三个 feature，**未启用 `socks` 或完整的 proxy 支持**。因此即使设置了 `HTTP_PROXY` / `HTTPS_PROXY`，该客户端也不会通过代理连接，而是直连目标（bypass 模式通过 hosts 劫持来兜底）。

   源码位置：
   - `codex-rs/rmcp-client/Cargo.toml` (lines 24-28) — feature 配置
   - `codex-rs/rmcp-client/src/rmcp_client.rs` (lines 103-106) — 客户端初始化
   - `codex-rs/core/src/mcp/mod.rs` (lines 165-199) — codex_apps bootstrap 路径

   **相关 Issue**：[openai/codex#16360](https://github.com/openai/codex/issues/16360)（已上报，暂无修复）。

2. **代理 IP 的 TLS 阻断**（第二层 — bypass 路径的限制）

   即使 bypass 成功劫持了 DNS 和 TCP（hosts 重定向 + 端口转发），上游代理 IP 在与 `chatgpt.com` 的 Cloudflare 边缘节点进行 TLS 握手时被拒绝（`SSL_ERROR_SYSCALL` / `tls handshake eof`）。

   注意：这不是 Cloudflare 对代理 IP 的无差别封禁——同一代理访问 `icanhazip.com`（也走 Cloudflare）的 TLS 完全正常。阻断是**针对特定 OpenAI 域名的 TLS 层面检测**。

#### 影响范围

| 功能 | 受影响 | 说明 |
|---|---|---|
| Codex Agent / Chat | 否 | 核心功能使用 WebSocket 连接 `api.openai.com`，走 `HTTP_PROXY` 正常 |
| 代码生成 / Review | 否 | 标准 API 调用不受影响 |
| 插件市场（Slack 等） | **是** | 依赖 `codex_apps` MCP server |
| MCP 工具（自定义） | 否 | 用户自定义 MCP server 不受影响 |

#### 解决方案

```bash
# 方案 1（推荐）：禁用 apps feature
codex features disable apps

# 方案 2：等待 OpenAI 修复
# Issue #16360 需要 codex 更新 rmcp-client 的 reqwest feature 配置
# 或支持通过代码配置 proxy URL

# 如需恢复插件功能
codex features enable apps
```

#### 长期展望

OpenAI 可能采取的修复路径：
1. 在 `codex-rmcp-client` 的 `Cargo.toml` 中启用 reqwest 的 proxy 相关 feature
2. 或为 codex_apps 添加独立的 proxy 配置项（类似 `global_proxy`）
3. 或允许通过 codex config.toml 为 MCP server 指定 proxy

### api.openai.com TLS 握手失败

```
✗ api.openai.com HTTPS — TLS handshake failed
```

CONNECT 隧道建立成功（DNS 本地解析工作正常），但 TLS 握手阶段被拒绝。这是特定代理 IP 在 OpenAI/Cloudflare 边缘节点的信誉限制，非 codex-relay 可控。

验证方法：
```bash
# 直接测试 CONNECT 隧道
curl -v -x http://127.0.0.1:PORT https://icanhazip.com -o /dev/null

# 查看 codex 连通性
codex-relay proxy check
```

### bypass 启动失败

```
listen EADDRNOTAVAIL: address not available 127.0.0.2:443
```

macOS 默认未配置 127.0.0.2 回环地址。当前版本已使用 127.0.0.1。

### PID 文件权限问题

bypass 守护进程以 root 运行，PID 文件属主为 root。`isBypassRunning()` 使用 `ps -p PID` 检测（而非 `process.kill(pid, 0)`），避免权限不足误判。

## 环境变量

codex-relay `run` 命令自动设置以下环境变量：

| 变量 | 值 | 说明 |
|---|---|---|
| HTTP_PROXY | http://127.0.0.1:PORT | HTTP 代理 |
| HTTPS_PROXY | http://127.0.0.1:PORT | HTTPS 代理 |
| WS_PROXY | http://127.0.0.1:PORT | WebSocket 代理 |
| WSS_PROXY | http://127.0.0.1:PORT | 安全 WebSocket 代理 |
| NO_PROXY | localhost,127.0.0.1,::1,.local | 本地连接绕过代理 |

## 代理解析优先级

1. 本地代理守护进程（如已启动） — 首选，自带 DNS 本地解析
2. `HTTP_PROXY` 等环境变量
3. `~/.codex-relay/config.json` 持久化配置

## 依赖

- Node.js >= 18（零 npm 依赖，仅使用 `net`、`dns`、`child_process` 等内置模块）
- `curl` — 连通性测试
- npm — 安装 Codex CLI
- macOS/Linux
