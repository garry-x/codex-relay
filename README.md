# codex-relay

OpenAI Codex CLI 代理包装器 — 通过 VPS 转发器将 codex 流量路由到 OpenAI。

## 架构

```
codex CLI  ──→  HTTP_PROXY  ──→  VPS forwarder  ──→  static proxy  ──→  OpenAI
  本机          Tailscale IP      (VPS, Tailscale)        (上游代理)
```

- **codex-relay**（本机）：配置代理、注入环境变量、透传 codex CLI
- **codex-relay-forward**（VPS）：TCP CONNECT 转发器，接收请求后通过上游静态代理转发
- **Tailscale**：本机 ↔ VPS 的 WireGuard 加密隧道，无需 SSH/CA 证书/TLS 终止

## 快速开始

```bash
# 1. 安装
codex-relay install

# 2. 配置代理（指向 VPS 的 Tailscale IP:端口）
codex-relay proxy set http://<vps-tailscale-ip>:8443

# 3. 验证连通性
codex-relay proxy check

# 4. 运行 codex
codex-relay run chat
# 或直接透传:
codex-relay chat
```

## 命令

| 命令 | 用途 |
|---|---|
| `proxy set <url>` | 配置代理 URL，保存到 `~/.codex-relay/config.json` |
| `proxy show` | 显示当前代理配置和生效状态 |
| `proxy unset` | 清除代理配置 |
| `proxy check [--url URL] [--timeout S]` | 全链路诊断：代理配置、curl、连通性、npm、codex |
| `vps setup <user@host> [--key path]` | 部署 `codex-relay-forward` 到 VPS |
| `vps proxy set <url>` | 设置 VPS 上游静态代理 |
| `vps proxy show` | 显示 VPS 上游代理 |
| `vps start\|stop\|status\|logs` | 管理 VPS 转发器 |
| `install [--force]` | 安装 codex-relay + Codex CLI |
| `install --update` | 更新 Codex CLI |
| `install --version X` | 安装指定版本 Codex CLI |
| `run <args...>` | 注入代理环境变量后运行 codex |
| `<anything>` | 直接透传至 codex CLI |

## VPS 部署

### 1. 环境准备

- Node.js >= 18
- Tailscale（与本地组网）
- 上游静态代理（本机无法直连 OpenAI 时使用）

### 2. 安装 codex-relay-forward

```bash
scp codex-relay-forward root@vps:/usr/local/bin/
chmod +x /usr/local/bin/codex-relay-forward
```

### 3. 配置上游代理

```bash
# 方式 A：环境变量
export FORWARD_PROXY=http://user:pass@static-proxy:8080

# 方式 B：config.json（推荐）
mkdir -p ~/.codex-relay
cat > ~/.codex-relay/config.json << 'EOF'
{
  "http": "http://user:pass@static-proxy:8080",
  "https": "http://user:pass@static-proxy:8080"
}
EOF
```

### 4. 启动

```bash
# 前台测试（显式监听 Tailscale IP 或 0.0.0.0）
codex-relay-forward <vps-tailscale-ip>:8443

# 后台运行
nohup codex-relay-forward <vps-tailscale-ip>:8443 &
```

输出示例：
```
[codex-relay-forward] <vps-tailscale-ip>:8443 → http://***@static-proxy:8080
```

### 5. systemd 持久化

```ini
[Unit]
Description=codex-relay TCP forwarder
After=network.target

[Service]
ExecStart=/usr/local/bin/codex-relay-forward <vps-tailscale-ip>:8443
Restart=always
RestartSec=5
Environment=FORWARD_PROXY=http://user:pass@static-proxy:8080

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now codex-relay-forward
```

### 6. Tailscale ACL（可选）

限制只有本机可访问 VPS 转发端口：

```json
{
  "acls": [
    {"action": "accept", "src": ["tag:client"], "dst": ["tag:vps:8443"]}
  ]
}
```

## 代理解析优先级

1. `HTTPS_PROXY` / `HTTP_PROXY` 环境变量
2. `~/.codex-relay/config.json` 中 `http` / `https` 字段

## 配置文件

```
~/.codex-relay/
└── config.json    # 代理配置（本机和 VPS 通用格式）
```

```json
{
  "http": "http://<vps-tailscale-ip>:8443",
  "https": "http://<vps-tailscale-ip>:8443"
}
```

本机和 VPS 使用同一格式：
- **本机**：指向 VPS Tailscale IP
- **VPS**：指向上游静态代理

## 故障排查

```bash
# 完整诊断
codex-relay proxy check

# 手动测试转发链路
curl -v --proxy http://<vps-tailscale-ip>:8443 https://api.openai.com -o /dev/null

# 检查 VPS forwarder 状态
ssh root@vps "ss -tlnp | grep 8443"

# 查看 codex 自身健康
codex-relay run doctor
```

## 环境依赖

### 本机（客户端）

| 依赖 | 版本要求 | 用途 |
|---|---|---|
| Node.js | >= 18 | 运行 codex-relay（`net`, `fs`, `path`, `os`, `child_process`, `crypto` 均为内置模块，零 npm 依赖） |
| npm | 任意 | 安装 Codex CLI（`npm install -g @openai/codex`） |
| curl | 任意 | `proxy check` 连通性诊断 |
| Tailscale | 任意 | 与 VPS 建立 WireGuard 加密隧道 |
| 操作系统 | macOS / Linux | Windows 未测试 |

### VPS（转发服务器）

| 依赖 | 版本要求 | 用途 |
|---|---|---|
| Node.js | >= 18 | 运行 codex-relay-forward（仅 `net`, `fs`, `path`, `os` 内置模块） |
| Tailscale | 任意 | 与本机建立 WireGuard 加密隧道 |
| 操作系统 | Linux | 推荐 Ubuntu 20.04+ / Debian 11+ |

### 网络要求

| 链路 | 协议 | 说明 |
|---|---|---|
| 本机 → VPS | Tailscale (WireGuard) | UDP，需要 Tailscale 组网 |
| VPS → 上游代理 | TCP | HTTP CONNECT 隧道 |
| 上游代理 → OpenAI | TCP + TLS | 代理转发 |

### 环境变量

| 变量 | 作用域 | 说明 |
|---|---|---|
| `HTTP_PROXY` / `HTTPS_PROXY` | 本机 | 优先于 config.json，指向 VPS Tailscale IP |
| `FORWARD_PROXY` | VPS | forwarder 使用的上游代理，优先于 config.json |
| `FORWARD_LISTEN` | VPS | forwarder 监听地址，默认 `127.0.0.1:8443`；VPS 部署时建议显式传 Tailscale IP |
| `FORWARD_ALLOW` | VPS | 允许 CONNECT 的目标，逗号分隔；默认 `api.openai.com:443,chatgpt.com:443,auth.openai.com:443,cdn.openai.com:443` |
| `NODE_EXTRA_CA_CERTS` | — | 不再需要（不进行 TLS 终止） |

## 安全说明

- `~/.codex-relay` 会以 `0700` 创建，`config.json` 会以 `0600` 写入，避免代理账号密码被其他本机用户读取。
- 日志和 `proxy show` 会脱敏 `user:pass@proxy` 中的认证信息。
- `codex-relay-forward` 默认只监听 `127.0.0.1:8443`。在 VPS 上运行时请显式监听 Tailscale IP，例如 `codex-relay-forward <vps-tailscale-ip>:8443`。
- `codex-relay-forward` 默认只允许连接常见 OpenAI/Codex 相关域名。如需扩展：

```bash
export FORWARD_ALLOW="api.openai.com:443,chatgpt.com:443,*.openai.com:443"
```

## 开发检查

```bash
npm run check
npm test
```
