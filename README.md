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
---
## 模式二：Split 代理（低延迟跨区域中继）

**适用场景**：本机与目标服务器之间网络延迟高（如跨太平洋），需要通过一台同区域 VPS 做 TLS 卸载，避免 TLS 握手在高延迟链路上多次往返。

```
codex  ──→  本地 TLS 代理  ──[SSH 加密隧道]──→  VPS Edge 代理  ──→  OpenAI
              ↑ TLS 在本地完成 (0ms)                ↑ TLS 在同区域完成 (~80ms)
```

Split 模式的核心原理：把 TLS 握手拆成两段——本地段（localhost，0ms），VPS 段（同区域，~80ms），中间通过 SSH 隧道传输明文 HTTP。

### 配置流程

#### 第一步：在 VPS 上启动 Edge 代理

```bash
# 1. 把 codex-relay 复制到 VPS
scp codex-relay root@your-vps:/usr/local/bin/

# 2. 如果 VPS 需要通过代理访问外网，配置 edge 上游代理
ssh root@your-vps
codex-relay split proxy set http://user:pass@vps-proxy:8080   # 可选

# 3. 启动 edge proxy（自动检测 edge 模式）
codex-relay split start
```

Edge 代理接收到目标服务器的 HTTPS 连接请求（如 api.openai.com），若配置了静态代理则通过代理转发，否则在同区域内直连。

#### 第二步：在本机启动本地代理（自动建立 SSH 隧道）

```bash
# 一条命令：自动建立 SSH 隧道 + 启动本地 TLS 代理
codex-relay split start --ssh root@your-vps
```

首次运行自动生成本地 CA 证书，后续复用。SSH 隧道 PID 记录到 `~/.codex-relay/split-tunnel.pid`，重新启动时会检测并复用。

如需手动管理 SSH 隧道：

```bash
ssh -N -f -L 19090:127.0.0.1:19090 root@your-vps
codex-relay split start --edge 127.0.0.1:19090
```

#### 第三步：配置并使用

```bash
# 1. 配置代理指向本地 split proxy
codex-relay proxy set http://127.0.0.1:18443

# 2. 查看运行状态
codex-relay split status

# 3. 诊断验证
codex-relay split check

# 4. 通过代理运行 codex
codex-relay run chat
```

`codex-relay run` 会自动注入 `NODE_EXTRA_CA_CERTS` 让 codex 信任本地 CA 证书。

### 涉及命令

| 命令 | 用途 |
|---|---|
| `split proxy set <url>` | 配置 edge 上游静态代理 |
| `split proxy show / unset` | 查看 / 清除 edge 代理配置 |
| `split start [user@host]` | 启动守护进程（自动识别 local/edge 模式） |
| `split stop` | 停止本地 + 远端守护进程 |
| `split status` | 查看 local、edge、SSH 隧道状态 |
| `split logs` | 查看守护进程日志 |
| `split check [--url URL] [--timeout S]` | 端到端诊断 |

### 日志

守护进程运行日志写入 `~/.codex-relay/logs/`：
- `split-local.log` — 本地代理：启动/停止、SSH 隧道建立/断开/自动重建
- `split-edge.log` — Edge 代理：启动/停止

通过 `codex-relay split logs` 查看。

### 生命周期

- `split start --ssh user@host` 自动建立 SSH 隧道并记录 PID
- 重新启动时检测隧道 PID 是否存活，存活则复用
- 隧道意外断开后本地守护进程每 30s 自动检测并重建
- `split stop` 优雅退出：关闭本地代理 → 终止 SSH 隧道 → 清理 PID 文件
- `split stop` 优雅退出：关闭本地代理 → 终止 SSH 隧道 → 清理 PID 文件
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


  Split 代理:
    split start [--edge] [--ssh user@host]  启动 edge 或本地守护进程
    split stop                              停止所有守护进程和 SSH 隧道
    split status                            查看守护进程状态
    split check [--edge <host:port>]        端到端诊断

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
├── config.json          # 代理配置
├── split-edge.pid       # Split edge 守护进程 PID
├── split-edge.heartbeat # Split edge 心跳
├── split-local.pid      # Split local 守护进程 PID
├── split-local.heartbeat # Split local 心跳
├── split-tunnel.pid     # SSH 隧道进程 PID
├── logs/                 # 守护进程运行日志
│   ├── split-edge.log
│   └── split-local.log
└── certs/               # Split 代理 CA 证书 & 域名证书缓存
    ├── ca-key.pem
    ├── ca-cert.pem
    └── <hostname-sha>/
        ├── key.pem
        └── cert.pem
```
