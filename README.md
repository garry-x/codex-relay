# codex-relay

OpenAI Codex CLI 代理包装器。通过 VPS 上的轻量转发器将 codex 流量路由到 OpenAI。

## 架构

```
codex  →  HTTP_PROXY  →  VPS forwarder  →  static proxy  →  OpenAI
           (Tailscale)     (Tailscale)
```

VPS 上运行 `codex-relay-forward`，接受 HTTP CONNECT 请求并通过上游静态代理转发。本地到 VPS 的传输由 Tailscale（WireGuard）加密。不需要 TLS 终止、CA 证书、守护进程或 SSH 隧道。

## 快速开始

```bash
# 1. 安装
codex-relay install

# 2. 配置代理（指向 VPS 的 Tailscale IP）
codex-relay proxy set http://100.114.41.104:8443

# 3. 验证
codex-relay proxy check

# 4. 运行 codex
codex-relay run chat
# 或者直接:
codex-relay chat
```

## 命令

| 命令 | 用途 |
|---|---|
| `proxy set <url>` | 配置上游代理（保存到 ~/.codex-relay/config.json） |
| `proxy show` | 查看当前代理配置 |
| `proxy unset` | 清除代理配置 |
| `proxy check [--url URL] [--timeout S]` | 测试代理连通性 + 诊断 |
| `install [--force]` | 安装 codex-relay + codex CLI |
| `install --update` | 更新 codex CLI |
| `install --version X` | 安装指定版本 codex |
| `run <args...>` | 通过代理运行 codex |

任何不认识的命令直接透传至 codex CLI。

## VPS 部署

### 1. 安装 codex-relay-forward

```bash
# 复制到 VPS
scp codex-relay-forward root@vps:/usr/local/bin/
chmod +x /usr/local/bin/codex-relay-forward
```

### 2. 配置上游静态代理

```bash
# 方式 A: 环境变量
export FORWARD_PROXY=http://user:pass@company-proxy:8080

# 方式 B: config.json
mkdir -p ~/.codex-relay
echo '{"http":"http://user:pass@company-proxy:8080","https":"http://user:pass@company-proxy:8080"}' > ~/.codex-relay/config.json
```

### 3. 启动

```bash
# 前台测试（IP 设为 Tailscale IP）
codex-relay-forward 100.114.41.104:8443

# 后台运行
nohup codex-relay-forward 100.114.41.104:8443 &
```

### systemd 持久化

```ini
[Unit]
Description=codex-relay TCP forwarder
After=network.target

[Service]
ExecStart=/usr/local/bin/codex-relay-forward 100.114.41.104:8443
Restart=always
Environment=FORWARD_PROXY=http://user:pass@company-proxy:8080

[Install]
WantedBy=multi-user.target
```

## 代理解析优先级

`HTTPS_PROXY` 环境变量 > `proxy set` 配置

## 配置文件

```
~/.codex-relay/
└── config.json          # 代理配置
```

```json
{
  "http": "http://100.114.41.104:8443",
  "https": "http://100.114.41.104:8443"
}
```

## 依赖

- Node.js >= 18（零 npm 依赖）
- curl（用于 proxy check）
- npm（用于安装 Codex CLI）
- Tailscale（本地 ↔ VPS 加密隧道）
- macOS / Linux
