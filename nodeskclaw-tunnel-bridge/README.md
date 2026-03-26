# nodeskclaw-tunnel-bridge

NoDeskClaw tunnel bridge -- Python WebSocket client that connects non-OpenClaw runtimes (ZeroClaw, NanoBot) to the NoDeskClaw backend tunnel.

## 用途

OpenClaw 使用 TypeScript channel plugin (`openclaw-channel-nodeskclaw`) 连接 tunnel。ZeroClaw 和 NanoBot 无法运行 TS 插件，因此通过本 Python 包提供 tunnel 连接能力。

## 组件

| 模块 | 用途 | 运行方式 |
|------|------|----------|
| `client.py` | 核心 WebSocket tunnel 客户端 + `TunnelCallbacks` + 协作方法（共享） | 被其他模块引用 |
| `nanobot_channel.py` | NanoBot `BaseChannel` 插件 | NanoBot 通过 `entry_points` 自动发现 |
| `zeroclaw_bridge.py` | ZeroClaw 独立桥接 + HTTP collaboration sidecar | 作为后台进程运行 |
| `__main__.py` | CLI 入口 | `python -m nodeskclaw_tunnel_bridge --runtime zeroclaw` |

## TunnelCallbacks

`TunnelClient` 支持通过 `TunnelCallbacks` dataclass 接收连接生命周期事件：

- `on_auth_ok` -- 认证成功
- `on_auth_error(reason)` -- 认证失败
- `on_close` -- WebSocket 连接关闭
- `on_reconnecting(attempt)` -- 开始重连（含尝试次数）

ZeroClaw bridge 和 NanoBot channel 默认传入结构化日志 callbacks。

## 主动协作能力

`TunnelClient` 提供两个方法供 NanoBot / ZeroClaw 主动发起 agent 间协作：

- `send_collaboration(workspace_id, source_instance_id, target, text, *, depth=0)` -- 通过 tunnel 发送 `collaboration.message`，后端 `MessageBus` 负责路由到目标 agent
- `list_peers(workspace_id)` -- 调用后端 `/topology/reachable` API，返回当前 workspace 中所有可达的 agent / human / blackboard 列表

**NanoBot** 通过 channel 对象的 `send_collaboration(target, text)` 和 `list_peers()` 直接调用（`workspace_id` 自动从最近一次 `chat.request` 中获取）。

**ZeroClaw** 通过本地 HTTP sidecar 间接调用（见下方 sidecar 文档）。

## 环境变量

| 变量 | 用途 | 必填 |
|------|------|------|
| `NODESKCLAW_API_URL` | 后端 API 地址 | 是（和 `NODESKCLAW_TUNNEL_URL` 二选一） |
| `NODESKCLAW_TUNNEL_URL` | Tunnel WebSocket 地址 | 否（优先级高于 API_URL 推导） |
| `NODESKCLAW_INSTANCE_ID` | 实例 ID | 是 |
| `NODESKCLAW_TOKEN` | 认证 token | 是 |
| `ZEROCLAW_GATEWAY_URL` | ZeroClaw 本地地址（默认 `http://localhost:4511`） | 否 |
| `ZEROCLAW_BEARER_TOKEN` | ZeroClaw Bearer token | 否 |
| `NODESKCLAW_SIDECAR_PORT` | ZeroClaw collaboration sidecar 端口（默认 `18791`） | 否 |

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

## ZeroClaw Collaboration Sidecar

ZeroClaw 是 Rust runtime，无法直接调用 Python 方法。bridge 在启动时会在本地开启一个 HTTP sidecar，ZeroClaw 通过 HTTP 请求发起协作：

### `POST /collaboration/send`

发送协作消息给目标 agent。

```json
// Request body
{"target": "agent:assistant-01", "text": "Please review the latest report."}

// Response 200
{"ok": true}
```

### `GET /peers`

获取当前 workspace 中所有可达的 peer 列表。

```json
// Response 200
{"peers": [{"type": "agent", "entity_id": "...", "display_name": "assistant-01"}, ...]}
```

Sidecar 默认监听 `localhost:18791`，可通过 `NODESKCLAW_SIDECAR_PORT` 环境变量覆盖。

## @mention 回复控制

当 `chat.request` 携带 `no_reply: true` 时：

- **ZeroClaw**: 仍调用 `/webhook`（消息进入 session），但丢弃响应内容
- **NanoBot**: 仍注入消息到 AgentLoop（进入 session 上下文），但丢弃 AgentLoop 回复
