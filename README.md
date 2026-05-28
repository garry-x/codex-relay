# codex-relay

OpenAI Codex CLI 的 Node.js 包装器，支持 HTTP 代理配置、本地 DNS 预解析、多 IP 连通性测试、本地转发代理，解决廉价代理（如 proxy-cheap）无法访问 OpenAI API 的问题。

## 安装

```bash
./codex-relay install
```

自动选择可写的 bin 目录（优先 `/usr/local/bin`，其次 `~/.local/bin`、`~/bin`）。安装后建议确认目标目录已在 PATH 中。

## 依赖

- Node.js >= 18（零 npm 依赖，仅使用内置模块）
- `curl`（代理连通性测试）
- npm（安装 Codex CLI）

## 操作顺序指引（新手必读）

### 首次使用

```bash
# 1. 安装 codex-relay 到系统 PATH
codex-relay install

# 2. 安装 Codex CLI（如未安装）
codex-relay install          # 已安装则自动跳过

# 3. 配置上游代理
codex-relay proxy set http://user:pass@your-proxy.com:8080

# 4. 预解析 OpenAI 域名并测试连通性
codex-relay dns cache

# 5. 启动本地代理
codex-relay proxy start

# 6. 检查一切是否就绪
codex-relay proxy test

# 7. 运行 codex
codex-relay run
```

### 日常使用

```bash
# 启动代理
codex-relay proxy start

# 运行 codex
codex-relay run

# 检查代理健康状态
codex-relay proxy status

# 停止代理
codex-relay proxy stop
```

### 更新

```bash
# 更新 codex-relay 自身
codex-relay install --force

# 更新 Codex CLI
codex-relay install --update
```

### 故障排查

```bash
# 全面诊断（12 项检查）
codex-relay proxy check

# 查看代理状态
codex-relay proxy status

# 查看请求日志
codex-relay proxy logs

# 重新缓存 DNS
codex-relay dns cache

# 重启代理
codex-relay proxy restart
```

### 代理 IP 变更

```bash
# 更换上游代理后，重新测试 DNS
codex-relay proxy set http://new-user:pass@new-proxy.com:8080
codex-relay dns cache
codex-relay proxy restart
```

## 快速上手

```bash
# 1. 配置上游代理
codex-relay proxy set http://user:pass@proxy.example.com:8080

# 2. 预解析 OpenAI 域名并测试连通性
codex-relay dns cache

# 3. 启动本地转发代理
codex-relay proxy start

# 4. 运行 codex
codex-relay run chat

# 5. 停止本地代理
codex-relay proxy stop
```

## 工作原理

```
codex → 127.0.0.1:LOCAL_PORT → 本地 DNS 解析 → 上游代理(IP 直连) → OpenAI
```

- codex 将本地代理视为普通 HTTP 代理，发送 `CONNECT api.openai.com:443`
- 本地代理**在本地**解析目标域名的所有 IP，并测试每个 IP 的连通性
- 本地代理向上游代理发送 `CONNECT <IP>:443`（上游无需解析域名）
- 优先使用已确认可通的 IP，失败时自动重试下一个（最多 2 个）
- 隧道建立后 transparently 转发 TCP 流量，支持 WebSocket

## 命令一览

```
codex-relay

  Commands:
    proxy     管理代理配置 & 本地代理守护进程
    dns       DNS 预解析与连通性测试
    install   安装或更新 Codex CLI
    run       通过代理运行 codex

  任何不认识的命令直接透传至 codex CLI
```

## proxy — 代理配置与管理

```bash
codex-relay proxy set <url>              # 配置上游代理
codex-relay proxy show                   # 查看当前配置和状态
codex-relay proxy unset                  # 清除代理配置
codex-relay proxy start                  # 启动本地代理
codex-relay proxy stop                   # 停止本地代理
codex-relay proxy restart                # 重启（stop + start）
codex-relay proxy status                 # 守护进程健康检查
codex-relay proxy test [--url URL]       # 连通性测试 + codex doctor
codex-relay proxy check                  # 全面诊断（9 项检查）
codex-relay proxy logs                   # 查看代理请求日志
```

### 连通性测试（`proxy test`）

```bash
codex-relay proxy test
```

输出包含代理连通性和 codex doctor 结果：

```
Proxy:    http://127.0.0.1:50129
Test URL: https://ipv4.icanhazip.com
Status:   200
Latency:  1100ms
Result:   OK — proxy is reachable

codex doctor:
  ✓ websocket: connected (HTTP 101 Switching Protocols)
    handshake result HTTP 101 Switching Protocols
  ✓ reachability: provider endpoints reachable over HTTP
    ChatGPT base URL reachable (HTTP 403)
```

### 全面诊断（`proxy check`）

```bash
codex-relay proxy check
```

检查上游配置、daemon 状态、DNS 缓存、curl、上游可达性、api.openai.com CONNECT + HTTPS、WebSocket 传输、npm、codex CLI、NO_PROXY。

### 守护进程状态（`proxy status`）

```bash
codex-relay proxy status

local daemon:   running (pid 71594, port 55678)
  heartbeat:    12s ago
```

### 请求日志（`proxy logs`）

```bash
codex-relay proxy logs
```

输出：

```
2026-05-27T07:50:41.529Z daemon started, pid=71594
2026-05-27T07:50:41.841Z CONNECT chatgpt.com:443 → 172.64.155.209 OK
2026-05-27T07:50:42.123Z CONNECT api.openai.com:443 → 172.66.0.243 OK
```

## dns — DNS 预解析与连通性测试

### 缓存并测试所有 OpenAI 域名

```bash
codex-relay dns cache
```

输出（每个 IP 显示 CONNECT 测试结果：✓ 通过 / ✗ 失败）：

```
[codex-relay] caching & testing DNS for OpenAI domains...
  api.openai.com      → 162.159.140.245, 172.66.0.243  [✓ ✓]
  chatgpt.com         → 172.64.155.209, 104.18.32.47   [✓ ✓]
```

### 解析单个域名

```bash
codex-relay dns resolve api.openai.com
# → api.openai.com → 162.159.140.245, 172.66.0.243
```

### 查看缓存的 DNS 记录

```bash
codex-relay dns show
```

输出（✓ 可通 / ✗ 不可通 / · 未测试）：

```
api.openai.com      ✓ 162.159.140.245, ✓ 172.66.0.243  (4m ago)
chatgpt.com         ✓ 172.64.155.209, ✓ 104.18.32.47   (4m ago)
```

本地代理运行时遇到未缓存的域名会自动补缓存。守护进程每 5 分钟自动刷新 DNS 并重新测试所有 IP。

## run — 运行 Codex

```bash
codex-relay run chat              # 显式运行
codex-relay chat                  # 直接透传（效果相同）
codex-relay generate "Hello, world"
```

自动设置以下环境变量：

| 变量 | 值 |
|---|---|
| HTTP_PROXY / HTTPS_PROXY | `http://127.0.0.1:PORT` |
| WS_PROXY / WSS_PROXY | `http://127.0.0.1:PORT` |
| NO_PROXY | `localhost,127.0.0.1,::1,.local` |

## install

```bash
codex-relay install               # 安装 codex-relay + Codex CLI
codex-relay install --force       # 强制安装（不询问已存在时是否覆盖）
codex-relay install --update      # 仅更新 Codex CLI
codex-relay install --version X   # 安装指定版本
```

## 代理解析优先级

本地代理守护进程（如已启动） > `HTTP_PROXY` 环境变量 > `proxy set` 配置

## 配置文件

所有数据存储在 `~/.codex-relay/` 下：

```
~/.codex-relay/
├── config.json          # 上游代理配置
├── dns.json             # DNS 解析缓存（多 IP + 测试结果）
├── proxy.pid            # 本地代理进程 PID
├── proxy.port           # 本地代理监听端口
├── proxy.log            # 请求日志 + 守护进程生命周期
└── proxy.heartbeat      # 本地代理心跳时间戳
```

### config.json

```json
{
  "http": "http://user:pass@proxy.example.com:8080",
  "https": "http://user:pass@proxy.example.com:8080",
  "provider_url": "https://proxy-cheap.com/api/proxies"
}
```

### dns.json

```json
{
  "api.openai.com": {
    "ips": [
      {"ip": "172.66.0.243", "ok": true, "testedAt": 1748310400000},
      {"ip": "162.159.140.245", "ok": false, "testedAt": 1748310400000}
    ],
    "ts": 1748310400000
  }
}
```
