# codex-relay

OpenAI Codex CLI 的代理包装器。提供两种代理模式，解决特定网络环境下 codex 无法直接访问 OpenAI API 的问题。

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
#    --upstream 支持多个上游，按顺序 fallback
#    direct 表示中间服务器直连目标（不经过代理）
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
  --listen 0.0.0.0:8443 \
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
codex-relay proxy set https://<TOKEN>@relay.example.com:8443

# 3. 验证连通性
codex-relay proxy check

# 4. 通过代理运行 codex
codex-relay run
```

### 涉及命令

| 命令 | 用途 |
|---|---|
| `chain config --listen --upstream [--tls-cert] [--tls-key]` | 保存中转配置 |
| `chain token generate` | 生成 token，hash 写入配置，明文仅输出一次 |
| `chain token show / unset` | 查看 / 清除 token |
| `chain start / stop / restart` | 管理中转守护进程 |
| `chain status` | 查看守护进程状态 |
| `chain logs` | 查看请求日志 |
| `chain serve --listen --upstream [--token]` | 前台运行中转服务 |

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
    chain config --listen --upstream   保存中转配置
    chain token generate               生成访问 token
    chain serve --listen --upstream    前台运行
    chain start / stop / restart       后台守护进程
    chain status / logs                状态与日志

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
└── chain.heartbeat      # 链式中转心跳
```
