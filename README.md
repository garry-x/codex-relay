# codex-relay

OpenAI Codex CLI 的 Node.js 包装器，支持 HTTP 代理配置、本地 DNS 预解析、本地转发代理，解决廉价代理（如 proxy-cheap）无法访问 OpenAI API 的问题。

## 安装

```bash
./codex-relay install
```

自动选择可写的 bin 目录（优先 `/usr/local/bin`，其次 `~/.local/bin`、`~/bin`）。安装后建议确认目标目录已在 PATH 中。

## 依赖

- Node.js >= 18（零 npm 依赖，仅使用内置模块）
- `curl`（代理连通性测试）
- npm（安装 Codex CLI）

## 快速上手

```bash
# 1. 配置上游代理
codex-relay proxy set http://user:pass@proxy.example.com:8080

# 2. 预解析 OpenAI 域名（缓存到本地）
codex-relay dns cache

# 3. 启动本地转发代理（后台守护进程）
codex-relay proxy start

# 4. 运行 codex
codex-relay run chat

# 5. 停止本地代理
codex-relay proxy stop
```

## 工作原理

上游代理（如 proxy-cheap）通常会过滤 `api.openai.com` 的 DNS 解析，导致 codex 无法通过代理访问 OpenAI。codex-relay 启动一个本地转发代理来解决这个问题：

```
codex → 127.0.0.1:LOCAL_PORT → 本地 DNS 解析 → 上游代理(IP 直连) → OpenAI
```

- codex 将本地代理视为普通 HTTP 代理，发送 `CONNECT api.openai.com:443`
- 本地代理**在本地**解析 `api.openai.com` 得到真实 IP
- 本地代理向上游代理发送 `CONNECT <IP>:443`（上游无需解析域名）
- 隧道建立，codex 正常通信

## 命令一览

```
codex-relay

  Commands:
    proxy     管理代理配置 & 本地代理守护进程
    dns       DNS 预解析与缓存
    install   安装或更新 OpenAI Codex CLI
    run       通过代理运行 codex

  任何不认识的命令直接透传至 codex CLI
```

### 无参运行

```bash
$ codex-relay
# 输出帮助信息
```

## proxy — 代理配置

### 设置上游代理

```bash
codex-relay proxy set http://user:pass@proxy.example.com:8080
```

### 查看当前配置

```bash
codex-relay proxy show
```

输出示例（本地代理运行中）：

```
HTTP proxy (config): http://user:pass@48.45.165.225:47453
Local forward proxy running on 127.0.0.1:58594
```

### 测试代理连通性

```bash
# 默认测试 URL
codex-relay proxy test

# 自定义测试 URL 和超时
codex-relay proxy test --url https://httpbin.org/ip --timeout 5
```

输出示例：

```
Proxy:    http://proxy.example.com:8080
Test URL: https://ipv4.icanhazip.com
Status:   200
Latency:  1294ms
Result:   OK — proxy is reachable
```

### 启动本地转发代理

```bash
codex-relay proxy start
```

启动后自动作为后台守护进程运行，PID 和端口记录在 `~/.codex-relay/` 下。本地代理会：
- 对所有 CONNECT 请求做本地 DNS 解析
- 用 IP 地址向上游代理发起连接（绕过上游 DNS 过滤）
- 自动注入 `Proxy-Authorization` 认证头

### 停止本地代理

```bash
codex-relay proxy stop
```

### 清除代理配置

```bash
codex-relay proxy unset
```

## dns — DNS 预解析

### 缓存所有 OpenAI 域名

```bash
codex-relay dns cache
```

输出：

```
[codex-relay] caching DNS for OpenAI domains...
  api.openai.com                 → 162.159.140.245
  auth.openai.com                → 104.18.41.241
  chatgpt.com                    → 104.18.32.47
  platform.openai.com            → 172.64.154.211
  developers.openai.com          → 64.239.109.1
```

### 解析单个域名

```bash
codex-relay dns resolve api.openai.com
# → api.openai.com → 162.159.140.245
```

### 查看缓存的 DNS 记录

```bash
codex-relay dns show
```

输出：

```
api.openai.com                 → 162.159.140.245    (4m ago)
auth.openai.com                → 104.18.41.241      (4m ago)
chatgpt.com                    → 104.18.32.47       (4m ago)
```

本地代理运行时遇到未缓存的域名会自动补缓存。

## run — 运行 Codex

```bash
# 显式运行
codex-relay run chat

# 直接透传（效果相同）
codex-relay chat
codex-relay generate "Hello, world"
```

如果本地代理在运行，自动将 `HTTP_PROXY` 指向本地代理；否则使用上游代理直连。

## install — 安装 Codex CLI

```bash
# 安装最新版（npm install -g @openai/codex）
codex-relay install

# 安装指定版本
codex-relay install --version 0.1.0

# 更新已有安装
codex-relay install --update
```

代理设置会自动注入 npm 的安装进程。

## 查看版本

```bash
codex-relay --version
```

输出：

```
codex-relay 0.2.0
codex: codex-cli 0.133.0
```

## 代理解析优先级

`proxy set` 设置的上游代理 > `HTTP_PROXY` 环境变量 > 本地转发代理（如已启动则是首选）

## 配置文件

所有数据存储在 `~/.codex-relay/` 下：

```
~/.codex-relay/
├── config.json     # 上游代理配置
├── dns.json        # DNS 解析缓存
├── proxy.pid       # 本地代理进程 PID
└── proxy.port      # 本地代理监听端口
```

`config.json` 格式：

```json
{
  "http": "http://user:pass@proxy.example.com:8080",
  "https": "http://user:pass@proxy.example.com:8080",
  "provider_url": "https://proxy-cheap.com/api/proxies"
}
```
