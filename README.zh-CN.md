[English](README.md)

[![Discord](https://img.shields.io/discord/1483008731934359723?logo=discord&label=Discord&color=5865F2)](https://discord.gg/y5NKqcP6eY)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

# DeskClaw

1
**人与 AI，共同经营。** 开源的人机共营平台 -- 让人类的判断力与 AI 的执行力，共同经营每一份事业。

DeskClaw 是人与 AI 共同经营组织的平台。通过赛博办公室（Cyber Workspace），人与 AI 在同一个数字空间中作为经营伙伴协同运转 -- 人类提供战略判断，AI 提供不懈的执行力，共同创造单方无法实现的价值。

## 共同经营

我们相信，未来属于人与 AI 共同经营的组织 -- 不是主人与工具的关系，而是各自贡献不可替代价值的经营伙伴。

- **人类经营者**提供战略判断、创造性决策、价值观把控 -- 决定"做什么"和"为什么做"
- **AI 经营者**提供不知疲倦的执行力、模式识别、快速迭代 -- 把"怎么做"做到极致
- **赛博办公室**是共同经营的空间 -- 共享经营看板（黑板）、任务委派、实时协同，让人与 AI 的经营能力融为一体

## 核心概念

### 赛博办公室（Cyber Workspace）

人与 AI 共同经营的数字空间。六边形拓扑让经营团队的协作关系可视化；共享黑板是团队的经营看板；任务发布让人或 AI 都能将业务委派给最合适的经营伙伴。不是监控面板，而是经营发生的地方。

### 基因系统（Gene System）

对 AI 经营能力的投资。为 AI 装载新基因，就是为你的事业打开新的经营维度 -- 模块化能力包来自公共市场或企业私有库，按需组合，持续进化。经营什么样的事业，就装载什么样的基因。

### 弹性扩展（Elastic Scale）

经营规模的即时扩张。一键部署 AI 经营伙伴，K8s 集群或 Docker 本地环境均可。DeskClaw 处理底层基础设施，你专注于经营决策。

## 亮点

- **赛博办公室** -- 六边形拓扑经营空间，人与 AI 共同经营、共享经营看板、委派业务
- **基因系统** -- 模块化能力投资：从公共或私有市场为 AI 装载新的经营维度
- **一键扩容** -- 端到端扩展经营规模，SSE 实时推送进度
- **多集群经营** -- 跨集群编排、健康巡检、弹性伸缩，覆盖整个经营版图
- **企业认证** -- 飞书 SSO + 组织架构自动同步，让现有组织无缝融入平台

## 社区版 / 企业版

采用社区版（CE）/ 企业版（EE）双版本架构：

| | 社区版（CE） | 企业版（EE） |
|---|---|---|
| 协议 | Apache 2.0 | 商业许可 |
| 核心功能 | 实例部署、集群管理、日志监控、基因市场 | CE 全部 + 多组织、计费、高级审计 |
| 代码 | 本仓库 | 私有 `ee/` 目录 |

运行时通过 `FeatureGate` 自动检测 -- `ee/` 存在即 EE，否则 CE。功能清单定义在 `features.yaml`。

**技术实现**：后端 Factory 抽象层 + Hook 事件总线；前端 Stub + Vite Alias Override。

## 技术架构

```mermaid
graph TD
    Human["人类经营者"] --> Portal["用户门户 (CE + EE)"]
    Human --> AdminUI["管理后台 (EE)"]
    Portal --> API["后端 API 中枢<br>Python 3.12 + FastAPI"]
    AdminUI --> API

    API --> DB[(PostgreSQL)]
    API --> CW["赛博办公室<br>黑板 / 拓扑 / 任务委派"]
    API --> Gene["基因系统<br>公共市场 + 企业私有库"]
    API --> Compute["K8s / Docker"]

    Compute --> Runtime["AI 运行时<br>OpenClaw / ZeroClaw / Nanobot"]
    Runtime <-->|"经营通道 (SSE)"| API
    Runtime --> LLM["LLM 代理"] --> Providers["OpenAI / Anthropic / Gemini / ..."]

    AIPartners["AI 经营伙伴"] -.->|"共同经营"| CW
```

### 项目结构

```
DeskClaw/
├── nodeskclaw-portal/             # 用户门户 -- Vue 3 + Tailwind CSS（CE + EE）
├── nodeskclaw-backend/            # API 服务 -- Python 3.12 + FastAPI + SQLAlchemy
├── nodeskclaw-llm-proxy/          # LLM 代理 -- Python + FastAPI
├── nodeskclaw-artifacts/          # Docker 镜像与部署制品
├── openclaw-channel-nodeskclaw/   # 赛博办公室经营通道插件
├── features.yaml                  # CE/EE 功能注册表
├── ee/                            # 企业版（私有）
│   └── nodeskclaw-frontend/      # 管理后台 -- Vue 3 + shadcn-vue（EE-only）
├── openclaw/                      # DeskClaw 运行时源码（外部）
└── vibecraft/                     # VibeCraft 源码（外部）
```

## 国际化

全栈国际化，覆盖 Portal、Admin、Backend 三端。

- 语言检测：`zh*` -> `zh-CN`，`en*` -> `en-US`，回退 `en-US`
- 错误展示：优先 `message_key` 本地翻译，缺失时回退 `message`
- 后端契约：`code` + `error_code` + `message_key` + `message` + `data`

## 快速开始

### Docker Compose 部署（推荐）

内置 PostgreSQL，无需外部数据库，一键启动完整平台。

```bash
# CE 版
docker compose up -d

# EE 版（含管理后台）
docker compose -f docker-compose.yml -f docker-compose.ee.yml up -d

# 可选：自定义时区、密钥等
# cp .env.example .env && vi .env
```

| 服务 | 地址 |
|---|---|
| 用户门户（Portal） | http://localhost |
| 后端 API | http://localhost:4510 |
| 管理后台（EE） | http://localhost:8001 |

**初始账号** -- 首次启动时，后端会自动创建管理员账号并生成随机密码，打印在日志中：

```bash
docker compose logs nodeskclaw-backend | grep -A4 "初始账号"
```

| 版本 | 默认账号 | 自定义环境变量 |
|---|---|---|
| CE | `admin` | `INIT_ADMIN_ACCOUNT` |
| EE（额外创建） | `deskclaw-admin` | `INIT_EE_ADMIN_ACCOUNT` |

首次登录后会要求修改密码。在修改密码之前，每次重启都会重新生成随机密码。

如需使用外部数据库替代内置 PostgreSQL，在项目根目录创建 `.env` 设置 `DATABASE_URL`，然后仅启动所需服务：

```bash
echo 'DATABASE_URL=postgresql+asyncpg://user:pass@your-rds:5432/nodeskclaw' > .env
docker compose up -d nodeskclaw-backend portal
```

### 本地开发

#### 前置条件

| 依赖 | 说明 |
|---|---|
| Python >= 3.12 + [uv](https://docs.astral.sh/uv/) | 后端运行时与包管理器 |
| Node.js >= 18 + npm | 前端运行时 |
| PostgreSQL | 数据库（或使用下方 `--docker-pg` 选项） |

#### 1. 配置

```bash
cd nodeskclaw-backend
cp .env.example .env
# 编辑 .env，填写 DATABASE_URL、JWT_SECRET 等
```

#### 2. 一键启动

```bash
./dev.sh              # 自动检测：ee/ 存在 -> EE，否则 -> CE
./dev.sh ce           # 强制 CE 模式（后端 + Portal）
./dev.sh ee           # 强制 EE 模式（后端 + Portal + Admin）
./dev.sh --docker-pg  # 用 Docker 启动 PostgreSQL（无需本地安装 PG）
./dev.sh --fresh      # 强制重新安装所有依赖
```

脚本自动处理依赖安装，以带颜色的日志前缀启动所有服务，Ctrl+C 统一清理。`--docker-pg` 会自动启动一个本地 PostgreSQL 容器。

| 模式 | 服务 | 端口 |
|------|------|------|
| CE | 后端 + Portal | 4510, 4517 |
| EE | 后端 + Portal + Admin | 4510, 4517, 4518 |

<details>
<summary>手动启动（备选）</summary>

**后端：**

```bash
cd nodeskclaw-backend
uv sync
uv run uvicorn app.main:app --reload --port 4510
```

API 地址 `http://localhost:4510` | Swagger 文档 `http://localhost:4510/docs` | 首次启动自动迁移数据库。

**前端（Portal）：**

```bash
cd nodeskclaw-portal
npm install && npm run dev
```

Portal 地址 `http://localhost:4517` | `/api` 自动代理到后端。

**前端（Admin，EE-only）：**

```bash
cd ee/nodeskclaw-frontend
npm install && npm run dev
```

Admin 地址 `http://localhost:4518` | `/api` 和 `/stream` 自动代理到后端。

</details>

#### 3. 登录

首次启动时，后端会在终端输出中直接打印初始管理员凭据：

```
========================================
  超管初始账号
  账号: admin
  密码: <随机生成>
  请登录后立即修改密码
========================================
```

打开 `http://localhost:4517`（Portal）或 `http://localhost:4518`（Admin，EE），使用打印的凭据登录。首次登录后会要求修改密码。

## 升级

### Docker Compose

所有业务服务均为本地构建，升级即拉取最新代码后重新构建。

```bash
# 1. 备份数据库
docker compose exec postgres pg_dump -U nodeskclaw nodeskclaw > backup_$(date +%Y%m%d).sql

# 2. 拉取目标版本
git pull origin main          # 最新代码
# git checkout v0.9.0         # 或指定 release tag

# 3. 重新构建并启动
docker compose build
docker compose up -d

# EE 版
docker compose -f docker-compose.yml -f docker-compose.ee.yml build
docker compose -f docker-compose.yml -f docker-compose.ee.yml up -d
```

数据库迁移在后端启动时自动执行（Alembic `upgrade head`）。可通过以下命令确认迁移结果：

```bash
docker compose logs nodeskclaw-backend | grep -i "alembic\|migration\|upgrade"
```

### Kubernetes（通过 deploy/cli.sh）

K8s 部署由 `deploy/cli.sh` 管理，标准流程为**先部署到 Staging，再推广到 Production**。

**Staging** -- 构建镜像、推送到 registry、滚动更新 Staging namespace：

```bash
./deploy/cli.sh deploy --tag v0.9.0
```

**Production** -- 复用已推送的镜像，更新 Production namespace（不重新构建）：

```bash
./deploy/cli.sh promote v0.9.0
```

数据库迁移在新的后端 Pod 启动时自动执行。完整 CLI 用法见 [deploy/README.md](deploy/README.md)。

### 升级注意事项

- **重大版本升级前请先备份数据库。**
- 查看 [GitHub Releases](https://github.com/patchwork-body/nodeskclaw/releases) 了解版本变更和不兼容改动。
- 如果数据库此前未由 Alembic 管理，首次升级前可能需要执行一次 `alembic stamp head`，详见[后端 README](nodeskclaw-backend/README.md)。

## 文档

| | |
|---|---|
| [后端](nodeskclaw-backend/README.md) | API 中枢、目录结构、环境变量 |
| [用户门户](nodeskclaw-portal/README.md) | 经营者入口前端 |
| [构建制品](nodeskclaw-artifacts/README.md) | DeskClaw 镜像构建与部署清单 |
| [经营通道](openclaw-channel-nodeskclaw/README.md) | 赛博办公室通信基础设施 |
| [LLM 代理](nodeskclaw-llm-proxy/README.md) | AI 智力供给中枢 |

## 社区

- [Discord](https://discord.gg/y5NKqcP6eY) -- 加入讨论、提问、分享反馈
- [GitHub Issues](https://github.com/patchwork-body/nodeskclaw/issues) -- Bug 报告与功能建议
- 微信 -- 扫描下方二维码加入开发者交流群

<img src=".github/wechat-group-qr.jpg" alt="DeskClaw 团队版开发者交流群" width="280">

## 贡献

欢迎提交 PR。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[Apache License 2.0](LICENSE)
