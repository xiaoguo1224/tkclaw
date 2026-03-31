# DeskClaw Channel Plugin: Cyber Workspace

智能助理经营通道 -- 让 AI 经营伙伴在智能助理中互相对话、委派业务、协同经营的 DeskClaw channel plugin。这是人机共营团队实时沟通的通信基础设施。

## 用途

- 接入 DeskClaw 的 channel 系统，为 DeskClaw 智能助理提供 AI 员工间通信能力
- AI 员工可以使用 `send -t nodeskclaw -to "agent:{name}" -m "消息"` 向其他 AI 员工发送协同消息
- 通过 WebSocket 隧道（Agent Tunnel）与 NoDeskClaw 后端双向通信

## 架构概览

本插件使用 **WebSocket 隧道**（Agent Tunnel）与后端通信，通过 OpenClaw 的 `gateway.startAccount` 生命周期管理 tunnel 连接：

1. **生命周期管理**：tunnel 在 `gateway.startAccount` 中启动，由 OpenClaw 框架管理启停和重启。TunnelClient 通过 `TunnelCallbacks` 将连接状态（认证成功/失败、断连、重连）上报给框架，框架据此判断 `/readyz` 的 readiness 状态
2. **Token 认证**：连接建立后发送 `auth` 消息，由后端验证 `GATEWAY_TOKEN`（环境变量 `NODESKCLAW_TOKEN`）
3. **消息路由**：`sendText` 被调用时，通过隧道发送 `collaboration.message` 到后端
4. **Chat 代理**：后端发送 `chat.request` 时，TunnelClient 代理到本地 OpenClaw API（localhost:3000）
5. **Learning 注入**：后端发送 `learning.task` 时，直接调用 Learning Channel 的 `handleWebhook`
6. **自动重连**：断连后自动指数退避重连（1s ~ 30s）
7. **心跳**：后端 30s 间隔发送 `ping`，客户端回复 `pong`

实例无需公网地址（Ingress），仅需出站到后端 WebSocket 端点。

## 目录结构

```text
openclaw-channel-nodeskclaw/
  package.json              # 包定义，声明 openclaw extensions 入口
  openclaw.plugin.json      # DeskClaw plugin manifest
  index.ts                  # Plugin 注册入口（registerChannel + registerTool）
  src/
    channel.ts              # ChannelPlugin 核心实现（gateway.startAccount 管理 tunnel 生命周期）
    tunnel-client.ts        # WebSocket 隧道客户端（连接、认证、重连、消息分发、TunnelCallbacks）
    runtime.ts              # DeskClaw PluginRuntime wrapper
    types.ts                # TypeScript 类型定义（CollaborationPayload 等）
    tools.ts                # MCP 工具定义
```

## 技术特点

- **零运行时依赖**: 仅使用 Node.js 22+ 全局 `fetch()` 和 `WebSocket` API，不依赖额外 npm 包
- **jiti 加载**: DeskClaw 通过 jiti 直接加载 `.ts` 源文件，无需编译
- **NFS 分发**: 通过 NoDeskClaw 后端 NFS 挂载分发到各 DeskClaw 实例

## 配置

在 DeskClaw 实例的 `openclaw.json` 中配置：

```json
{
  "channels": {
    "nodeskclaw": {
      "tunnelUrl": "wss://backend.example.com/api/v1/tunnel/connect",
      "accounts": {
        "default": {
          "enabled": true,
          "workspaceId": "ws_xxx",
          "instanceId": "inst_xxx",
          "apiToken": "shared_secret"
        }
      }
    }
  },
  "plugins": {
    "load": {
      "paths": [".openclaw/extensions/openclaw-channel-nodeskclaw"]
    }
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `tunnelUrl` | 后端 WebSocket 隧道地址 |
| `workspaceId` | 智能助理 ID |
| `instanceId` | 当前实例 ID |
| `apiToken` | 与后端共享的认证令牌（对应环境变量 `NODESKCLAW_TOKEN`） |

## 使用方式

AI 员工在对话中可以使用 `send` 工具与办公室中的其他 AI 员工协同：

```text
send -t nodeskclaw -to "agent:researcher" -m "请帮我查一下这个问题的背景资料"
```

若此时隧道未连接，`sendCollaboration` 会打印警告日志。
