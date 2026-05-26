# codex-relay

OpenAI Codex CLI 的 Python 包装器，自动配置 HTTP 代理（支持 proxy-cheap 等代理服务），支持安装/升级 Codex CLI，并可直接透传调用。

## 安装

```bash
pip install codex-relay
```

或者从源码安装：

```bash
git clone https://github.com/user/codex-relay.git
cd codex-relay
pip install -e .
```

## 前置依赖

- Python >= 3.10
- Node.js / npm（用于 `install` 命令安装 Codex CLI）

## 命令一览

```
codex-relay

  Commands:
    config    管理代理配置
    install   安装或更新 OpenAI Codex CLI
    run       通过代理运行 codex

  任何不认识的命令会直接透传至 codex CLI
```

### 无参运行

```bash
$ codex-relay
# 输出帮助信息
```

## 代理配置

### 设置代理

```bash
# 手动设置 HTTP/HTTPS 代理
codex-relay config proxy set http://user:pass@proxy.example.com:8080

# 设置代理服务商 URL（如 proxy-cheap），每次运行自动获取代理
codex-relay config proxy set https://proxy-cheap.com/api/proxies
```

### 查看当前代理

```bash
codex-relay config proxy show
```

### 测试代理连通性

```bash
# 使用默认测试 URL（https://api.openai.com）
codex-relay config proxy test

# 自定义测试 URL
codex-relay config proxy test --url https://httpbin.org/ip

# 自定义超时时间
codex-relay config proxy test --timeout 5
```

输出示例：

```
Proxy:    http://proxy.example.com:8080
Test URL: https://api.openai.com
Status:   200
Latency:  342.5ms
Result:   OK — proxy is reachable
```

### 从代理服务商获取代理列表

```bash
codex-relay config proxy fetch https://proxy-cheap.com/api/proxies
```

### 清除代理配置

```bash
codex-relay config proxy unset
```

## 代理解析优先级

1. **环境变量** — `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`
2. **配置文件** — `~/.codex-relay/config.yaml` 中的持久化设置
3. **自动获取** — 从代理服务商 URL 动态拉取

## 安装 Codex CLI

```bash
# 安装最新版
codex-relay install

# 安装指定版本
codex-relay install --version 0.1.0

# 更新已有安装
codex-relay install --update
```

通过 npm 全局安装 `@openai/codex`，代理设置自动生效。

## 运行 Codex

```bash
# 显式运行
codex-relay run chat
codex-relay run generate "Hello, world"

# 直接透传（效果相同）
codex-relay chat
codex-relay generate "Hello, world"
```

运行时会自动注入代理环境变量，输出中会提示当前使用的代理地址：

```
[codex-relay] using proxy: http://proxy.example.com:8080
```

## 查看版本

```bash
codex-relay --version
```

输出：

```
codex-relay 0.1.0
codex: codex-cli 0.133.0
```

## 配置文件

代理配置持久化在 `~/.codex-relay/config.yaml`，格式如下：

```yaml
http: http://proxy.example.com:8080
https: http://proxy.example.com:8080
provider_url: https://proxy-cheap.com/api/proxies
```
