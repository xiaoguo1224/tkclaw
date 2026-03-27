[中文](README.zh-CN.md)

[![Discord](https://img.shields.io/discord/1483008731934359723?logo=discord&label=Discord&color=5865F2)](https://discord.gg/y5NKqcP6eY)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

# DeskClaw

**Co-operate with AI.** The open-source platform where humans and AI run businesses together -- from strategy to execution.

DeskClaw is the operating platform for human-AI co-managed organizations. Through Cyber Workspaces, humans and AI operate as partners in a shared digital space -- humans provide strategic judgment, AI delivers relentless execution, and together they build something neither could alone.

## Co-operating

We believe the future belongs to organizations where humans and AI co-operate -- not as master and tool, but as partners who each bring irreplaceable value to the business.

- **Human operators** bring strategic judgment, creative decisions, and value alignment -- deciding *what to do* and *why*
- **AI operators** bring tireless execution, pattern recognition, and rapid iteration -- pushing *how to do it* to the extreme
- **Cyber Workspace** is where co-operating happens -- a shared operations board (blackboard), task delegation, and real-time coordination that fuses human and AI capabilities into one

## Core Concepts

### Cyber Workspace

The digital space where humans and AI co-operate. Hexagonal topology visualizes your operating team's relationships; the shared blackboard serves as the team's operations dashboard; task publishing lets any partner -- human or AI -- delegate work to whoever is best suited. Not a monitoring panel, but the place where business happens.

### Gene System

Investment in AI operating capabilities. Loading a new Gene onto an AI partner opens a new dimension for your business -- modular capability packages from a public marketplace or your private enterprise library, composable on demand, continuously evolving. The business you run determines the Genes you load.

### Elastic Scale

Instant expansion of operating capacity. One-click deployment of AI operating partners on Kubernetes clusters or local Docker environments. DeskClaw handles the infrastructure so you can focus on operating decisions.

## Highlights

- **Cyber Workspace** -- Hexagonal topology space where human and AI partners co-operate, share an operations board, and delegate tasks
- **Gene System** -- Modular capability investment: load new business dimensions onto AI partners from a public or private marketplace
- **One-Click Scale** -- Expand your operating capacity end-to-end, with SSE real-time progress streaming
- **Multi-Cluster Operations** -- Cross-cluster orchestration, health checks, and elastic scaling across your business footprint
- **Enterprise Auth** -- Feishu SSO with automatic org structure sync, bringing your existing organization into the platform

## CE / EE

Dual-edition architecture: Community Edition / Enterprise Edition.

| | CE (Community) | EE (Enterprise) |
|---|---|---|
| License | Apache 2.0 | Commercial |
| Features | Instance deploy, cluster management, log monitoring, gene marketplace | All of CE + multi-org, billing, advanced audit |
| Code | This repository | Private `ee/` directory |

Runtime auto-detection via `FeatureGate` -- if `ee/` exists it runs as EE, otherwise CE. Feature registry defined in `features.yaml`.

**Technical implementation**: Backend Factory abstraction + Hook event bus; Frontend Stub + Vite Alias Override.

## Architecture

```mermaid
graph TD
    Human["Human Operators"] --> Portal["Portal (CE + EE)"]
    Human --> AdminUI["Admin Console (EE)"]
    Portal --> API["Backend API Hub<br>Python 3.12 + FastAPI"]
    AdminUI --> API

    API --> DB[(PostgreSQL)]
    API --> CW["Cyber Workspace<br>Blackboard / Topology / Delegation"]
    API --> Gene["Gene System<br>Public + Enterprise Marketplace"]
    API --> Compute["K8s / Docker"]

    Compute --> Runtime["AI Runtime<br>OpenClaw / ZeroClaw / Nanobot"]
    Runtime <-->|"Channel Plugin (SSE)"| API
    Runtime --> LLM["LLM Proxy"] --> Providers["OpenAI / Anthropic / Gemini / ..."]

    AIPartners["AI Operating Partners"] -.->|"co-operate"| CW
```

### Project Layout

```
DeskClaw/
├── nodeskclaw-portal/             # User Portal -- Vue 3 + Tailwind CSS (CE + EE)
├── nodeskclaw-backend/            # API Server -- Python 3.12 + FastAPI + SQLAlchemy
├── nodeskclaw-llm-proxy/          # LLM Proxy -- Python + FastAPI
├── nodeskclaw-artifacts/          # Docker images & deploy manifests
├── openclaw-channel-nodeskclaw/   # Cyber Workspace channel plugin
├── openclaw-channel-dingtalk/     # DingTalk channel plugin (Stream protocol)
├── features.yaml                  # CE/EE feature registry
├── ee/                            # Enterprise Edition (private)
│   └── nodeskclaw-frontend/      # Admin Console -- Vue 3 + shadcn-vue (EE-only)
├── openclaw/                      # DeskClaw runtime source (external)
└── vibecraft/                     # VibeCraft source (external)
```

## i18n

Full-stack internationalization covering Portal, Admin, and Backend.

- Language detection: `zh*` -> `zh-CN`, `en*` -> `en-US`, fallback `en-US`
- Error display: prefer `message_key` local translation, fall back to `message` when missing
- Backend contract: `code` + `error_code` + `message_key` + `message` + `data`

## Quick Start

### Docker Compose (recommended for deployment)

Deploy the full platform with a built-in PostgreSQL -- no external database required.

```bash
# 1. Clone the repo (for docker-compose.yml and .env.example)
git clone https://github.com/NoDeskAI/nodeskclaw.git
cd nodeskclaw

# 2. Configure -- set DESKCLAW_VERSION to the release you want
cp .env.example .env
# Edit .env as needed (DESKCLAW_VERSION is required for pulling pre-built images)

# 3. Pull pre-built images and start (recommended)
docker compose pull
docker compose up -d

# EE (with Admin console)
docker compose -f docker-compose.yml -f docker-compose.ee.yml pull
docker compose -f docker-compose.yml -f docker-compose.ee.yml up -d

# Alternative: build from source (for development or customization)
# docker compose up --build -d
```

| Service | URL |
|---|---|
| Portal | http://localhost |
| Backend API | http://localhost:4510 |
| LLM Proxy | http://localhost:4511 |
| Admin (EE) | http://localhost:8001 |

**Initial credentials** -- on first startup the backend creates an admin account with a random password and prints it to the log:

```bash
docker compose logs nodeskclaw-backend | grep -A4 "Initial"
```

| Edition | Default account | Env var to customize |
|---|---|---|
| CE | `admin` | `INIT_ADMIN_ACCOUNT` |
| EE (additional) | `deskclaw-admin` | `INIT_EE_ADMIN_ACCOUNT` |

You will be prompted to change the password on first login. The random password is regenerated on every restart until you change it.

To use an external database instead of the built-in PostgreSQL, create a `.env` at project root with your `DATABASE_URL` and start only the services you need:

```bash
echo 'DATABASE_URL=postgresql+asyncpg://user:pass@your-rds:5432/nodeskclaw' > .env
docker compose up -d nodeskclaw-backend portal
```

### Kubernetes

For production or multi-node environments. Requires a K8s cluster, a container registry, and an external PostgreSQL database.

#### Prerequisites

| Dependency | |
|---|---|
| Kubernetes cluster | 1.24+ with Ingress Controller (e.g. ingress-nginx) |
| Container registry | Any Docker V2 registry (Docker Hub, AWS ECR, GCR, etc.) |
| PostgreSQL | External database (e.g. AWS RDS, GCP Cloud SQL) |
| kubectl | Configured with access to your cluster |
| Docker | For building images locally |

#### 1. Configure Registry & Context

```bash
# Create deploy/.env.local (git-ignored)
cat > deploy/.env.local <<'EOF'
REGISTRY="your-registry.example.com/deskclaw"
KUBE_CONTEXT="your-kubectl-context"
EOF

# Login to your container registry
docker login your-registry.example.com
```

#### 2. Prepare Backend Environment Variables

```bash
cp nodeskclaw-backend/.env.example nodeskclaw-backend/.env
# Edit .env -- fill in DATABASE_URL, JWT_SECRET, ENCRYPTION_KEY, etc.
# Minimum required:
#   DATABASE_URL=postgresql+asyncpg://user:pass@your-rds:5432/nodeskclaw
#   JWT_SECRET=<random-secret>
#   ENCRYPTION_KEY=<32-byte-base64-key>
```

#### 3. Initialize the Cluster

Creates the namespace, uploads `.env` as a K8s Secret, and applies base Deployment + Service manifests:

```bash
./deploy/cli.sh init                    # Default: staging namespace
./deploy/cli.sh init --prod             # Production namespace
```

#### 4. Build & Deploy

```bash
./deploy/cli.sh deploy                  # Build all images + rolling update (staging)
./deploy/cli.sh deploy --prod           # Deploy to production (interactive confirm)
./deploy/cli.sh deploy backend          # Deploy a single component
```

#### 5. Configure Ingress

Edit `deploy/k8s/ingress.yaml` -- replace `example.com` hosts with your actual domains, then apply:

```bash
kubectl --context <CTX> -n <NS> apply -f deploy/k8s/ingress.yaml
```

The Ingress defines three hosts (configure as needed):

| Ingress | Default host | Backend service |
|---|---|---|
| Portal | `console.example.com` | portal (80) + backend API (8000) |
| Admin (EE) | `admin.example.com` | admin (80) + backend API (8000) |
| LLM Proxy | `llm-proxy.example.com` | llm-proxy (80) |

See [deploy/README.md](deploy/README.md) for full CLI reference, image tagging, and the release/promote workflow.

### Local Development

#### Prerequisites

| Dependency | |
|---|---|
| Python >= 3.12 + [uv](https://docs.astral.sh/uv/) | Backend runtime & package manager |
| Node.js >= 18 + npm | Frontend runtime |
| PostgreSQL | Database (or use `--docker-pg` below) |

#### 1. Configure

```bash
cd nodeskclaw-backend
cp .env.example .env
# Edit .env -- fill in DATABASE_URL, JWT_SECRET, etc.
```

#### 2. One-command Start

```bash
./dev.sh              # Auto-detect: ee/ exists -> EE, otherwise -> CE
./dev.sh ce           # Force CE mode (backend + portal)
./dev.sh ee           # Force EE mode (backend + portal + admin)
./dev.sh --docker-pg  # Start a Docker PostgreSQL (no local PG install needed)
./dev.sh --fresh      # Force reinstall all dependencies
```

The script handles dependency installation, starts all services with colored log prefixes, and cleans up on Ctrl+C. `--docker-pg` launches a local PostgreSQL container automatically.

| Mode | Services | Ports |
|------|----------|-------|
| CE | backend + llm-proxy + portal | 4510, 4511, 4517 |
| EE | backend + llm-proxy + portal + admin | 4510, 4511, 4517, 4518 |

<details>
<summary>Manual Start (alternative)</summary>

**Backend:**

```bash
cd nodeskclaw-backend
uv sync
uv run uvicorn app.main:app --reload --port 4510
```

API at `http://localhost:4510` | Swagger at `http://localhost:4510/docs` | Auto-migration on first boot.

**Frontend (Portal):**

```bash
cd nodeskclaw-portal
npm install && npm run dev
```

Portal at `http://localhost:4517` | `/api` auto-proxy to backend.

**Frontend (Admin, EE-only):**

```bash
cd ee/nodeskclaw-frontend
npm install && npm run dev
```

Admin at `http://localhost:4518` | `/api` and `/stream` auto-proxy to backend.

</details>

#### 3. Sign In

On first startup the backend prints the initial admin credentials directly in the terminal output:

```
========================================
  Initial admin account
  Account: admin
  Password: <random>
  Please change your password after login
========================================
```

Open `http://localhost:4517` (Portal) or `http://localhost:4518` (Admin, EE) and sign in with the printed credentials. You will be prompted to change the password on first login.

## Upgrade

### Docker Compose

```bash
# 1. Back up the database
docker compose exec postgres pg_dump -U nodeskclaw nodeskclaw > backup_$(date +%Y%m%d).sql

# 2. Update DESKCLAW_VERSION in .env to the target release
# DESKCLAW_VERSION=v0.9.0

# 3. Pull new images and restart
git pull origin main
docker compose pull
docker compose up -d

# EE
docker compose -f docker-compose.yml -f docker-compose.ee.yml pull
docker compose -f docker-compose.yml -f docker-compose.ee.yml up -d

# Alternative: rebuild from source
# docker compose up --build -d
```

Database migrations run automatically on backend startup (Alembic `upgrade head`). Verify with:

```bash
docker compose logs nodeskclaw-backend | grep -i "alembic\|migration\|upgrade"
```

### Kubernetes (via deploy/cli.sh)

K8s deployments are managed by `deploy/cli.sh`. The typical workflow is **deploy to staging first, then promote to production**.

**Staging** -- build images, push to registry, and rolling-update the staging namespace:

```bash
./deploy/cli.sh deploy --tag v0.9.0
```

**Production** -- reuse the already-pushed images and update the production namespace (no rebuild):

```bash
./deploy/cli.sh promote v0.9.0
```

Database migrations run automatically when the new backend pod starts. See [deploy/README.md](deploy/README.md) for full CLI usage and options.

### Upgrade Notes

- **Back up your database** before any major version upgrade.
- Check [GitHub Releases](https://github.com/patchwork-body/nodeskclaw/releases) for release notes and breaking changes.
- If your database was not previously managed by Alembic, you may need to run `alembic stamp head` once before upgrading. See [Backend README](nodeskclaw-backend/README.md) for details.

## Documentation

| | |
|---|---|
| [Backend](nodeskclaw-backend/README.md) | API hub, directory layout, env vars |
| [Portal](nodeskclaw-portal/README.md) | User portal frontend |
| [Artifacts](nodeskclaw-artifacts/README.md) | DeskClaw image build & deploy manifests |
| [Channel Plugin](openclaw-channel-nodeskclaw/README.md) | Cyber Workspace communication infrastructure |
| [DingTalk Plugin](openclaw-channel-dingtalk/README.md) | DingTalk channel via Stream protocol |
| [LLM Proxy](nodeskclaw-llm-proxy/README.md) | AI reasoning capability relay |

## Community

- [Discord](https://discord.gg/y5NKqcP6eY) -- Join the discussion, ask questions, share feedback
- [GitHub Issues](https://github.com/NoDeskAI/nodeskclaw/issues) -- Bug reports and feature requests
- WeChat -- Scan the QR code below to join the developer group; if the WeChat group is full, please use Discord above

<img src=".github/wechat-group-qr.jpg" alt="DeskClaw WeChat Developer Group" width="280">

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[Apache License 2.0](LICENSE)
