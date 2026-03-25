# nodeskclaw-tunnel-bridge

NoDeskClaw tunnel bridge -- Python WebSocket client that connects non-OpenClaw runtimes (ZeroClaw, NanoBot) to the NoDeskClaw backend tunnel.

## 用途

OpenClaw 使用 TypeScript channel plugin (`openclaw-channel-nodeskclaw`) 连接 tunnel。ZeroClaw 和 NanoBot 无法运行 TS 插件，因此通过本 Python 包提供 tunnel 连接能力。

## 组件

| 模块 | 用途 | 运行方式 |
|------|------|----------|
| `client.py` | 核心 WebSocket tunnel 客户端 + `TunnelCallbacks`（共享） | 被其他模块引用 |
| `nanobot_channel.py` | NanoBot `BaseChannel` 插件 | NanoBot 通过 `entry_points` 自动发现 |
| `zeroclaw_bridge.py` | ZeroClaw 独立桥接 | 作为后台进程运行 |
| `__main__.py` | CLI 入口 | `python -m nodeskclaw_tunnel_bridge --runtime zeroclaw` |

## TunnelCallbacks

`TunnelClient` 支持通过 `TunnelCallbacks` dataclass 接收连接生命周期事件：

- `on_auth_ok` -- 认证成功
- `on_auth_error(reason)` -- 认证失败
- `on_close` -- WebSocket 连接关闭
- `on_reconnecting(attempt)` -- 开始重连（含尝试次数）

ZeroClaw bridge 和 NanoBot channel 默认传入结构化日志 callbacks。

## 环境变量

| 变量 | 用途 | 必填 |
|------|------|------|
| `NODESKCLAW_API_URL` | 后端 API 地址 | 是（和 `NODESKCLAW_TUNNEL_URL` 二选一） |
| `NODESKCLAW_TUNNEL_URL` | Tunnel WebSocket 地址 | 否（优先级高于 API_URL 推导） |
| `NODESKCLAW_INSTANCE_ID` | 实例 ID | 是 |
| `NODESKCLAW_TOKEN` | 认证 token | 是 |
| `ZEROCLAW_GATEWAY_URL` | ZeroClaw 本地地址（默认 `http://localhost:4511`） | 否 |
| `ZEROCLAW_BEARER_TOKEN` | ZeroClaw Bearer token | 否 |

## 安装

```bash
pip install .
```

## 使用

### ZeroClaw（独立进程）

在 ZeroClaw 容器的 entrypoint 中作为后台进程启动：

```bash
python3 -m nodeskclaw_tunnel_bridge --runtime zeroclaw &
```

**注意**：ZeroClaw 安全镜像（`Dockerfile.security`）必须安装 `python3-minimal`、`python3-pip` 和本包，否则 bridge 会静默失败。

### NanoBot（channel 插件）

安装包后，NanoBot 的 `ChannelManager` 通过 `entry_points` 自动发现 `NoDeskClawChannel`。
在 `nanobot.yaml` 中启用：

```yaml
channels:
  nodeskclaw:
    enabled: true
    allow_from: ["*"]
```

## @mention 回复控制

当 `chat.request` 携带 `no_reply: true` 时：

- **ZeroClaw**: 仍调用 `/webhook`（消息进入 session），但丢弃响应内容
- **NanoBot**: 仍注入消息到 AgentLoop（进入 session 上下文），但丢弃 AgentLoop 回复
