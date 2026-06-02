# codex-relay

OpenAI Codex CLI 的代理包装器。提供三种代理模式，解决特定网络环境下 codex 无法直接访问 OpenAI API 的问题。

## 安装

```bash
./codex-relay install
```

自动选择可写的 bin 目录（优先 `/usr/local/bin`，其次 `~/.local/bin`、`~/bin`）。

依赖：Node.js >= 18（零 npm 依赖）、`curl`、npm。

---

## 模式一：直连

**适用场景**：本机可以直接访问一个静态 HTTP 代理，通过它访问 OpenAI。

```
codex  ──→  静态代理  ──→  OpenAI
```

### 配置流程

```bash
# 1. 配置上游静态代理（用户名、密码、地址、端口）
codex-relay proxy set http://user:pass@your-proxy.com:8080

# 2. 验证代理连通性
codex-relay proxy check

# 3. 通过代理运行 codex
codex-relay run
```

之后日常使用只需 `codex-relay run`（或直接 `codex-relay chat`，效果相同）。更换代理时重新执行 `proxy set`。

### 涉及命令

| 命令 | 用途 |
|---|---|
| `proxy set <url>` | 配置上游代理，持久化到 `~/.codex-relay/config.json` |
| `proxy show` | 查看当前配置 |
| `proxy unset` | 清除代理配置 |
| `proxy check [--url URL] [--timeout S]` | 全面诊断：代理配置、连通性（延迟 + HTTP 状态码）、npm、codex CLI |
| `run <args...>` | 自动注入代理环境变量，运行 codex |

---

## 模式二：链式中转

**适用场景**：本机无法直接访问静态代理，需要经过一台中间服务器转发。

```
codex  ──→  链式中转服务器  ──→  静态代理  ──→  OpenAI
```

链式中转服务器是一个纯 TCP/HTTP 代理转发器：收到请求后加上认证信息转发给上游静态代理，不做 TLS 解密。

### 配置流程

#### 第一步：在中间服务器上部署中转服务

```bash
# 1. 安装 codex-relay
./codex-relay install

# 2. 生成访问 token（明文只输出这一次，配置文件保存 SHA-256 hash）
codex-relay chain token generate
# 输出: AbCdEf123456...  ← 复制此 token，后续本机配置需要

# 3. 保存中转配置
#    --upstream 可选：不传时自动使用 proxy set 的代理 URL
#    显式指定时支持多个上游 fallback，direct 表示直连目标
codex-relay chain config --listen 0.0.0.0:8080

# 或者显式指定上游：
codex-relay chain config \
  --listen 0.0.0.0:8080 \
  --upstream http://user:pass@static-proxy:8080,direct

# 4. 后台启动中转服务
codex-relay chain start

# 查看运行状态
codex-relay chain status
```

如果中间服务器有 TLS 证书，可保护客户端到中转服务器之间的链路：

```bash
codex-relay chain config \
  --listen 0.0.0.0:18443 \
  --upstream http://user:pass@static-proxy:8080,direct \
  --tls-cert /etc/codex-relay/fullchain.pem \
  --tls-key /etc/codex-relay/privkey.pem
codex-relay chain restart
```

#### 第二步：在本机配置

```bash
# 1. 安装 codex-relay（如果还未安装）
./codex-relay install

# 2. 配置代理指向中间服务器（token 以 Proxy-Authorization 形式传递）
codex-relay proxy set http://<TOKEN>@relay.example.com:8080

# 如果中间服务器启用了 TLS：
codex-relay proxy set https://<TOKEN>@relay.example.com:18443

# 3. 验证连通性
codex-relay proxy check

# 4. 通过代理运行 codex
codex-relay run
```

### 涉及命令

| 命令 | 用途 |
|---|---|
| `chain config --listen [--upstream] [--tls-cert] [--tls-key]` | 保存中转配置（--upstream 可选，默认复用 proxy set） |
| `chain token generate` | 生成 token，hash 写入配置，明文仅输出一次 |
| `chain token show / unset` | 查看 / 清除 token |
| `chain start / stop / restart` | 管理中转守护进程 |
| `chain status` | 查看守护进程状态 |
| `chain logs` | 查看请求日志 |

---

---
## 模式三：Split 代理（低延迟跨区域中继）

**适用场景**：本机与目标服务器之间网络延迟高（如跨太平洋），需要通过一台同区域 VPS 做 TLS 卸载，避免 TLS 握手在高延迟链路上多次往返。

```
codex  ──→  本地 TLS 代理  ──[SSH 加密隧道]──→  VPS Edge 代理  ──→  OpenAI
              ↑ TLS 在本地完成 (0ms)                ↑ TLS 在同区域完成 (~80ms)
```

**核心原理**：模式二（链式中转）的 TLS 握手是端到端的（codex ↔ OpenAI），每个握手包都要跨洋往返 3 次（~700ms）。Split 模式把 TLS 拆成两段：本地段（localhost，0ms）+ VPS 段（同区域，~80ms），中间通过 SSH 隧道传输明文 HTTP。

### 配置流程

#### 第一步：在 VPS 上启动 Edge 代理

```bash
# 1. 把 codex-relay 复制到 VPS
scp codex-relay root@your-vps:/usr/local/bin/

# 2. 在 VPS 上启动 edge proxy（监听 127.0.0.1，仅 SSH 隧道可访问）
codex-relay split edge start
```

Edge 代理维护到目标（如 api.openai.com）的 HTTPS 连接，所有 TLS 握手在同区域内完成。

#### 第二步：在本机启动本地代理（自动建立 SSH 隧道）

```bash
# 一条命令：自动建立 SSH 隧道 + 启动本地 TLS 代理
codex-relay split local start --edge 127.0.0.1:119090 --host your-vps

# 首次运行自动生成本地 CA 证书，后续复用
# --host 触发自动 SSH 隧道，隧道 PID 记录到 ~/.codex-relay/split-tunnel.pid
# 重新启动时会检测已存在的隧道并复用
```

本地代理接收 codex 的 CONNECT 请求，在本地完成 TLS 握手（localhost，接近 0ms），将解密后的 HTTP 请求通过 SSH 隧道转发给 VPS edge。

**手动 SSH 隧道**（可选，不使用 `--host` 时）：

```bash
ssh -N -f -L 19090:127.0.0.1:119090 root@your-vps
codex-relay split local start --edge 127.0.0.1:119090
```

#### 第三步：配置并使用

```bash
# 1. 配置代理指向本地 split proxy
codex-relay proxy set http://127.0.0.1:118443

# 2. 查看运行状态
codex-relay split local status

# 3. 诊断验证
codex-relay split check

# 4. 通过代理运行 codex
codex-relay run chat
```

`codex-relay run` 会自动注入 `NODE_EXTRA_CA_CERTS` 让 codex 信任本地 CA 证书。

### 延迟对比

| 阶段 | 链式中转 (模式二) | Split 代理 (模式三) |
|---|---|---|
| TLS 握手 | 端到端跨洋 720-1887ms | localhost 3-5ms |
| HTTP 请求/响应 | ~458ms (跨洋) | ~458ms (SSH 隧道) |
| VPS → OpenAI TLS | — | ~82ms (同区域) |
| **总计** | **~1600ms** | **~550ms** |

### 涉及命令

| 命令 | 用途 |
|---|---|
| `split edge start [--listen <host:port>]` | 后台启动 VPS edge 守护进程 |
| `split edge stop / restart / status` | 管理 edge 守护进程 |
| `split local start --edge <host:port> --host <vps>` | 后台启动本地 TLS 代理（自动 SSH 隧道，`--host` 可选） |
| `split local stop / restart / status` | 管理本地守护进程，stop 时自动清理 SSH 隧道 |
| `split check [--edge <host:port>] [--url URL] [--timeout S]` | 端到端诊断：CA 证书、edge 可达性、TLS 终止、完整链路 |

### 生命周期

- `split local start --host <vps>` 自动建立 SSH 隧道并记录 PID
- 重新启动时检测隧道 PID 是否存活，存活则复用
- 若端口被占用但 PID 已死，自动释放端口并重建隧道
- `split local stop` 或 Ctrl+C 时优雅退出：关闭本地代理 → 终止 SSH 隧道 → 清理 PID 文件

### 架构安全

- Edge 代理只监听 `127.0.0.1`，不暴露公网端口
- SSH 隧道提供加密传输（本地 → VPS）
- 本地 CA 私钥仅存在于本机 `~/.codex-relay/certs/`
- TLS 证书按域名动态生成，缓存复用

---
## 命令总览

```
codex-relay

  直连模式:
    proxy set <url>                    配置上游代理
    proxy show                         查看当前配置
    proxy unset                        清除配置
    proxy check [--url URL] [--timeout S]  全面诊断 & 连通性测试

  链式中转:
    chain config --listen [--upstream]  保存中转配置（--upstream 可选，复用 proxy set）
    chain token generate               生成访问 token
    chain start / stop / restart       后台守护进程
    chain status / logs                状态与日志

  Split 代理:
    split edge start|stop|restart|status  管理 VPS edge 守护进程
    split local start|stop|restart|status 管理本地 TLS 代理 (--host 自动隧道)
    split check [--edge <host:port>]      端到端诊断

  通用:
    install [--force|--update]         安装 / 更新
    run <args...>                      通过代理运行 codex

  任何不认识的命令直接透传至 codex CLI
```

---

## run — 运行 Codex

```bash
codex-relay run chat                    # 显式运行
codex-relay chat                        # 直接透传（效果相同）
```

自动注入的环境变量：

| 变量 | 值 |
|---|---|
| `HTTP_PROXY` / `HTTPS_PROXY` | 配置的代理 URL |
| `WS_PROXY` / `WSS_PROXY` | 配置的代理 URL |
| `NO_PROXY` | `localhost,127.0.0.1,::1,.local` |

## 代理解析优先级

`HTTP_PROXY` 环境变量 > `proxy set` 配置

## 配置文件

```
~/.codex-relay/
├── config.json          # 代理配置 & 链式中转配置
├── chain.pid            # 链式中转 PID
├── chain.log            # 链式中转请求日志
├── chain.heartbeat      # 链式中转心跳
├── split-edge.pid       # Split edge 守护进程 PID
├── split-edge.heartbeat # Split edge 心跳
├── split-local.pid      # Split local 守护进程 PID
├── split-local.heartbeat # Split local 心跳
├── split-tunnel.pid     # SSH 隧道进程 PID
└── certs/               # Split 代理 CA 证书 & 域名证书缓存
    ├── ca-key.pem
    ├── ca-cert.pem
    └── <hostname-sha>/
        ├── key.pem
        └── cert.pem
```
