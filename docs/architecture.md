# codex-relay 架构与原理

## 三种代理模式

### 直连模式

```
codex → 静态代理 → OpenAI
```

codex-relay 将配置的静态代理 URL 通过环境变量（`HTTP_PROXY`、`HTTPS_PROXY` 等）注入 codex 进程。codex 的所有 HTTP/CONNECT 请求直接发给静态代理，由静态代理完成对 OpenAI 的访问。

- 无本地守护进程
- 无 DNS 解析或请求改写
- 仅做环境变量注入

### 链式中转模式

```
codex → 链式中转服务器 → 静态代理 → OpenAI
```

链式中转服务器是一个纯 TCP/HTTP 代理转发器，部署在中间服务器上：

```
┌─────────┐  HTTP_PROXY     ┌──────────────┐   CONNECT 域名:443  ┌──────────┐  TCP  ┌──────────┐
│  Codex  │ ───────────────→ │ chain relay  │ ───────────────────→ │ 静态代理  │ ────→ │ OpenAI   │
│   CLI   │  中间服务器 URL   │  relay server │   Proxy-Auth 注入    │ (proxy)  │       │ Servers  │
└─────────┘                  └──────────────┘                      └──────────┘       └──────────┘
```

核心行为：
- 接收客户端的 HTTP/CONNECT 请求
- 校验 `Proxy-Authorization`（token 认证）
- 注入上游静态代理的认证 header
- 将请求转发给上游静态代理
- **不修改请求目标、不做 DNS 解析、不做 TLS 解密**

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

**延迟优势**：链式中转模式 TLS 握手需 3 次端到端跨洋往返（~700ms），Split 模式 TLS 在本地完成（~3ms）。

## 组件

### proxy — 代理配置与诊断

`proxy set` 将代理 URL 持久化到 `~/.codex-relay/config.json`。`run` 命令读取配置（或 `HTTP_PROXY` 环境变量）并注入 codex 进程。

- `proxy set <url>` — 保存代理配置
- `proxy show` — 显示当前配置和生效的代理
- `proxy unset` — 清除配置
- `proxy check [--url URL] [--timeout S]` — 全面诊断：代理配置、连通性（延迟 + HTTP 状态码）、npm、codex CLI

### chain relay — 链式中转服务器

部署在中间服务器上的后台守护进程：

- 监听 HTTP 代理端口，接受 `CONNECT` 和普通 HTTP 请求
- Token 认证：客户端 token 以 `Proxy-Authorization` header 传递，服务器端存储 SHA-256 hash
- 上游代理认证注入：将静态代理的凭证注入 `Proxy-Authorization`
- 多上游 fallback：按配置顺序尝试，任一成功即返回；未配置 `--upstream` 时自动复用 `proxy set` 的代理
- `direct` 上游：跳过静态代理，中间服务器直连目标
- TLS：支持 `--tls-cert` / `--tls-key` 加密客户端到中转服务器链路

### split relay — Split 代理

由两个协同进程组成：

**本地代理** (`split local`)：
- 监听 `127.0.0.1:18443`，作为 codex 的 HTTP 代理
- TLS 终止：用动态生成的域名证书完成与 codex 的 TLS 握手
- 通过 ALPN 强制 HTTP/1.1，简化转发
- 将解密后的 HTTP 通过 SSH 隧道转发给 edge 代理
- 首次运行自动生成 CA 证书（ECDSA P-256，10 年有效）

**Edge 代理** (`split edge`)：
- 监听 `127.0.0.1:19090`（仅 SSH 隧道可访问）
- 解析 `X-Target: host:port` 元数据头
- 建立到目标服务器的 TLS 连接（同区域，低延迟）
- `NODE_EXTRA_CA_CERTS` 自动注入，codex 信任本地 CA

**SSH 隧道**：
- `split local start --host <vps>` 自动建立，PID 追踪，优雅退出时清理
- 默认端口 19090，可自定义（同 edge 端口）

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

### 链式中转模式

```
codex 启动
  → codex-relay run 设置 HTTP_PROXY=http://token@relay:8080
  → codex 发送 CONNECT api.openai.com:443 到 relay:8080
  → Header 带 Proxy-Authorization: Basic <token>
  → chain relay 校验 token
  → chain relay 注入上游代理认证 header
  → chain relay 转发 CONNECT api.openai.com:443 到静态代理
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
├── config.json          # 代理配置 & 链式中转配置
├── chain.pid            # 链式中转进程 PID
├── chain.log            # 链式中转请求日志
├── chain.heartbeat      # 链式中转心跳时间戳
└── certs/               # Split 代理 CA 证书 & 按域名缓存
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

链式中转模式（config.json 在中间服务器上）：
```json
{
  "chain": {
    "listen": "0.0.0.0:8080",
    "upstreams": ["http://user:pass@static-proxy:8080", "direct"],
    "token_hash": "sha256:abc123...",
    "tls_cert": "/path/to/cert.pem",
    "tls_key": "/path/to/key.pem"
  }
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

### 链式中转日志

```bash
codex-relay chain logs
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
