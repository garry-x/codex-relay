# codex-relay 架构与原理

## 两种代理模式

### 直连模式

```
codex → 静态代理 → OpenAI
```

codex-relay 将配置的静态代理 URL 通过环境变量（`HTTP_PROXY`、`HTTPS_PROXY` 等）注入 codex 进程。codex 的所有 HTTP/CONNECT 请求直接发给静态代理，由静态代理完成对 OpenAI 的访问。

- 无本地守护进程
- 无 DNS 解析或请求改写
- 仅做环境变量注入

### Split 代理模式

```
codex → 本地 TLS 代理 → [SSH 隧道] → VPS Edge 代理 → OpenAI
```

将 TLS 握手拆为两段，避免高延迟链路上的多次往返：

```
┌─────────┐  HTTP_PROXY     ┌──────────────┐  明文 HTTP      ┌──────────────┐  HTTPS    ┌──────────┐
│  Codex  │ ───────────────→ │ 本地 TLS 代理 │ ───[SSH 隧道]──→ │ VPS Edge 代理 │ ────────→ │ OpenAI   │
│   CLI   │ localhost:18443  │ (TLS 终止)    │                  │ (连接池)       │           │ Servers  │
└─────────┘                  └──────────────┘                   └──────────────┘           └──────────┘
   TLS 握手:                       ↑                                ↑
   localhost → localhost (0ms)     TLS 段1: 本地完成                TLS 段2: 同区域完成 (~80ms)
```

核心行为：
- **本地代理**：接收 codex 的 CONNECT 请求，在本地完成 TLS 握手（localhost，0ms 延迟），解密 HTTP 流量
- **SSH 隧道**：传输明文 HTTP（已从 TLS 解密），单次跨洋往返即可完成请求
- **Edge 代理**：接收明文 HTTP，通过 HTTPS 连接池转发给 OpenAI（TLS 在同区域内完成，~80ms）
- 动态证书生成：首次连接域名时通过 openssl 生成对应证书，后续缓存复用

**延迟优势**：Split 模式将 TLS 握手在本地完成（~3ms），避免跨洋链路的高延迟多次往返。

## 组件

### proxy — 代理配置与诊断

`proxy set` 将代理 URL 持久化到 `~/.codex-relay/config.json`。`run` 命令读取配置（或 `HTTP_PROXY` 环境变量）并注入 codex 进程。

- `proxy set <url>` — 保存代理配置
- `proxy show` — 显示当前配置和生效的代理
- `proxy unset` — 清除配置
- `proxy check [--url URL] [--timeout S]` — 全面诊断：代理配置、连通性（延迟 + HTTP 状态码）、npm、codex CLI

### split relay — Split 代理

由两个协同进程组成：

**本地代理** (`split start --ssh user@host`)：
- 启动命令：`split start --ssh user@vps`，自动建立 SSH 隧道
- 监听 `127.0.0.1:18443`，作为 codex 的 HTTP 代理
- TLS 终止：用动态生成的域名证书完成与 codex 的 TLS 握手
- 通过 ALPN 强制 HTTP/1.1，简化转发
- 将解密后的 HTTP 通过 SSH 隧道转发给 edge 代理
- 首次运行自动生成 CA 证书（ECDSA P-256，10 年有效）

**Edge 代理** (`split start`)：
- 在 VPS 上运行，自动检测 edge 模式（无 SSH 配置 → edge）
- 监听 `127.0.0.1:19090`（仅 SSH 隧道可访问）
- 解析 `X-Target: host:port` 元数据头
- 若配置了 `proxy set`，通过静态代理连接目标；否则直连 TLS（同区域，低延迟）

**SSH 隧道**：
- `split start --ssh user@vps` 自动建立，PID 追踪，拆分时自动清理

**诊断** (`split check`)：
- 验证 openssl、CA 证书、edge 可达性
- 启动临时本地代理完成端到端连通性测试

## 请求流

### 直连模式

```
codex 启动
  → codex-relay run 设置 HTTP_PROXY=http://proxy:8080
  → codex 发送 CONNECT api.openai.com:443 到 proxy:8080
  → 静态代理建立隧道，转发 TLS 流量
```

### Split 代理模式

```
codex 启动
  → codex-relay run 设置 HTTP_PROXY=http://127.0.0.1:18443, NODE_EXTRA_CA_CERTS=...
  → codex 发送 CONNECT api.openai.com:443 到 127.0.0.1:18443
  → 本地代理回复 200，启动 TLS 握手（本地完成，0ms）
  → codex 发送 HTTPS 请求（已解密为明文 HTTP）
  → 本地代理添加 X-Target: api.openai.com:443 元数据头
  → 通过 SSH 隧道转发明文 HTTP 到 VPS edge:19090
  → edge 代理解析目标地址，建立 TLS 连接（同区域 ~80ms）
  → edge 代理转发 HTTP 请求并返回响应
  → 响应沿原路返回：edge → SSH 隧道 → 本地代理 → TLS 加密 → codex
```

## 配置文件

```
~/.codex-relay/
├── config.json            # 代理配置
├── split-edge.pid         # Split edge 守护进程 PID
├── split-edge.heartbeat   # Split edge 心跳
├── split-local.pid        # Split local 守护进程 PID
├── split-local.heartbeat  # Split local 心跳
├── split-tunnel.pid       # SSH 隧道进程 PID
└── certs/                 # Split 代理 CA 证书 & 按域名缓存
    ├── ca-key.pem
    ├── ca-cert.pem
    └── <hostname-sha>/
        ├── key.pem
        └── cert.pem
```

### config.json 结构

直连模式：
```json
{
  "http": "http://user:pass@proxy.example.com:8080",
  "https": "http://user:pass@proxy.example.com:8080"
}
```

## 故障排查

### proxy check 诊断

```bash
codex-relay proxy check
```

输出示例：

```
codex-relay proxy check

  ✓ proxy config (http://user:pass@host:8080)
  ✓ curl (available)
  ✓ proxy connectivity (HTTP 421, 1143ms → https://api.openai.com)
  ✓ npm (available)
  ✓ codex CLI (codex-cli 0.133.0)

5 OK, 0 issues
```

### 手动验证代理

```bash
# 测试代理是否可达
curl -v --proxy http://user:pass@host:8080 https://api.openai.com -o /dev/null

# 通过 codex-relay 测试
codex-relay proxy check
```


### split check 诊断

```bash
codex-relay split check
```

输出示例：

```
codex-relay split check

  ✓ openssl (available)
  ✓ CA certificate (/home/user/.codex-relay/certs/ca-cert.pem)
  ✓ curl (available)
  ✓ edge proxy (TCP 127.0.0.1:19090 open)
  ✓ split proxy chain (HTTP 421, 779ms → https://api.openai.com)

5 OK, 0 issues
```

## 环境变量

`run` 命令自动设置：

| 变量 | 值 |
|---|---|
| `HTTP_PROXY` / `HTTPS_PROXY` | 配置的代理 URL |
| `WS_PROXY` / `WSS_PROXY` | 配置的代理 URL |
| `NODE_EXTRA_CA_CERTS` | Split 代理 CA 证书路径（自动注入，仅当 proxy 指向 127.0.0.1 时） |
| `NO_PROXY` | `localhost,127.0.0.1,::1,.local` |

## 依赖

- Node.js >= 18（零 npm 依赖，内置模块：`net`、`tls`、`fs`、`crypto`、`child_process`）
- `openssl` — Split 代理证书生成
- `curl` — 连通性测试
- `ssh` — Split 代理隧道
- npm — 安装 Codex CLI
- macOS / Linux
