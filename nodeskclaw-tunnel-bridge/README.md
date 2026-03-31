# nodeskclaw-tunnel-bridge

NoDeskClaw tunnel bridge -- Python WebSocket client that connects non-OpenClaw runtimes (NanoBot) to the NoDeskClaw backend tunnel.

## 用途

OpenClaw 使用 TypeScript channel plugin (`openclaw-channel-nodeskclaw`) 连接 tunnel。NanoBot 无法运行 TS 插件，因此通过本 Python 包提供 tunnel 连接能力。

## 组件

| 模块 | 用途 | 运行方式 |
|------|------|----------|
| `client.py` | 核心 WebSocket tunnel 客户端 + `TunnelCallbacks` + 协作方法（共享） | 被其他模块引用 |
| `nanobot_channel.py` | NanoBot `BaseChannel` 插件 | NanoBot 通过 `entry_points` 自动发现 |
| `__main__.py` | CLI 入口（预留扩展） | `python -m nodeskclaw_tunnel_bridge --runtime <name>` |

## TunnelCallbacks

`TunnelClient` 支持通过 `TunnelCallbacks` dataclass 接收连接生命周期事件：

- `on_auth_ok` -- 认证成功
- `on_auth_error(reason)` -- 认证失败
- `on_close` -- WebSocket 连接关闭
- `on_reconnecting(attempt)` -- 开始重连（含尝试次数）

NanoBot channel 默认传入结构化日志 callbacks。

## 主动协作能力

`TunnelClient` 提供两个方法供 NanoBot 主动发起 agent 间协作：

- `send_collaboration(workspace_id, source_instance_id, target, text, *, depth=0)` -- 通过 tunnel 发送 `collaboration.message`，后端 `MessageBus` 负责路由到目标 agent
- `list_peers(workspace_id)` -- 调用后端 `/topology/reachable` API，返回当前 workspace 中所有可达的 agent / human / blackboard 列表

**NanoBot** 通过 channel 对象的 `send_collaboration(target, text)` 和 `list_peers()` 直接调用（`workspace_id` 自动从最近一次 `chat.request` 中获取）。

## 环境变量

| 变量 | 用途 | 必填 |
|------|------|------|
| `NODESKCLAW_API_URL` | 后端 API 地址 | 是（和 `NODESKCLAW_TUNNEL_URL` 二选一） |
| `NODESKCLAW_TUNNEL_URL` | Tunnel WebSocket 地址 | 否（优先级高于 API_URL 推导） |
| `NODESKCLAW_INSTANCE_ID` | 实例 ID | 是 |
| `NODESKCLAW_TOKEN` | 认证 token | 是 |

## 安装

```bash
pip install .
```

## 使用

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

- **NanoBot**: 仍注入消息到 AgentLoop（进入 session 上下文），但丢弃 AgentLoop 回复
