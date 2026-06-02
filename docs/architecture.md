# codex-relay 架构

## 整体架构

```
codex CLI  →  HTTP_PROXY  →  VPS forwarder (Tailscale)  →  static proxy  →  OpenAI
```

- **codex-relay**: 本机 CLI 包装器，负责代理配置、环境变量注入、codex 安装
- **codex-relay-forward**: VPS 上的 TCP CONNECT 转发器，通过上游静态代理转发请求
- **Tailscale**: 提供本机到 VPS 的 WireGuard 加密隧道

不再需要 TLS 终止、本地 CA 证书、守护进程、SSH 隧道。

## 请求流

```
codex 启动
  → codex-relay run 设置 HTTP_PROXY=http://<vps-tailscale-ip>:8443
  → codex 发送 CONNECT api.openai.com:443 到 <vps-tailscale-ip>:8443
  → VPS forwarder 接收 CONNECT，通过静态代理转发到 api.openai.com:443
  → 静态代理建立隧道，转发 TLS 流量
  → TLS 端到端 (codex ↔ api.openai.com)，VPS forwarder 不做解密
```

## 组件

### codex-relay — 本地 CLI

- `proxy set <url>` — 保存代理 URL 到 `~/.codex-relay/config.json`
- `proxy show` — 显示当前配置和生效的代理
- `proxy unset` — 清除配置
- `proxy check [--url URL] [--timeout S]` — 测试代理连通性
- `install` — 安装 codex-relay + Codex CLI
- `run <args...>` — 注入 HTTP_PROXY/HTTPS_PROXY 环境变量后运行 codex

### codex-relay-forward — VPS 转发器

部署在 VPS 上的轻量 TCP CONNECT 转发器：

- 监听 Tailscale IP 上的端口（如 `<vps-tailscale-ip>:8443`）
- 接收 HTTP CONNECT 请求
- 通过上游静态代理建立 CONNECT 隧道
- 双向转发 (pipe) 客户端和上游之间的数据
- 不解析、修改或解密流量
- 零 npm 依赖，~100 行代码

### 配置文件

```
~/.codex-relay/
└── config.json          # 代理配置
```

```json
{
  "http": "http://<vps-tailscale-ip>:8443",
  "https": "http://<vps-tailscale-ip>:8443"
}
```

## 依赖

- Node.js >= 18（net, fs, path, os, child_process）
- curl — 连通性测试
- npm — 安装 Codex CLI  
- Tailscale — 本地 ↔ VPS 加密隧道
