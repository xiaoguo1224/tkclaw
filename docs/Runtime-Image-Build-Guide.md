# Runtime Image Build Guide

> For developers: how to build, upgrade, and manage the container images that power AI agent instances in NoDeskClaw.

---

## 1. Overview

NoDeskClaw runs AI agent instances on **runtime engines**. Each engine ships as a standalone Docker image built from upstream package managers — not compiled from this repository's source code.

| Engine | Base Image | Install Source | Port | Use Case |
|--------|-----------|---------------|------|----------|
| **OpenClaw** | `node:22-bookworm-slim` | npm `openclaw` | 18789 | Full-featured AI Agent, TypeScript ecosystem |
| **Nanobot** | `python:3.13-slim-bookworm` | PyPI `nanobot-ai` | 18790 | Lightweight Python engine |

### Relation to Platform Components

```
nodeskclaw-artifacts/build.sh     ← Runtime engine images (this document)
deploy/cli.sh                     ← Platform component images (backend / portal / admin / llm-proxy)
```

These two build pipelines are completely independent.

### Two-Layer Image Structure

Each engine supports a Base + Security layered architecture:

```
┌──────────────────────────────┐
│  Security Layer (optional)   │  Tag: v2026.3.13-sec
│  FROM base + security plugin │
├──────────────────────────────┤
│  Base Layer                  │  Tag: v2026.3.13
│  System deps + engine + scripts │
└──────────────────────────────┘
```

| Layer | Dockerfile | Build Context | Description |
|-------|-----------|---------------|-------------|
| Base | `Dockerfile` | Engine directory (e.g. `openclaw-image/`) | Engine binary + entrypoint + config template |
| Security | `Dockerfile.security` | **Project root** | FROM base image + security layer code |

---

## 2. Quick Start

### Prerequisites

- Docker Desktop or Docker Engine (with BuildKit support)
- Apple Silicon users: the script automatically sets `--platform linux/amd64` (target cluster architecture)
- npm (OpenClaw version verification), python3 (Nanobot version detection)

### Unified Entry Point: `build.sh`

All engines use a single entry script at `nodeskclaw-artifacts/build.sh`:

```bash
cd nodeskclaw-artifacts

# Auto-detect latest version, build + push
./build.sh openclaw
./build.sh nanobot
./build.sh all                          # All engines

# Specify version
./build.sh openclaw --version 2026.3.13
./build.sh nanobot --version 0.1.4

# Build only, skip push
./build.sh openclaw --build-only

# Skip verification (slow on Apple Silicon due to QEMU emulation)
./build.sh openclaw --skip-verify

# Build all engines, no push, no verify
./build.sh all --build-only --skip-verify
```

### Automated Build Pipeline

```
1. Version detection (when --version is omitted)
   ├── OpenClaw → npm view openclaw versions
   └── Nanobot  → PyPI JSON API
        ↓
2. Version verification (OpenClaw checks npm registry)
        ↓
3. docker build --platform linux/amd64
        ↓
4. Tag: v{version} (e.g. v2026.3.13)
        ↓
5. Verify (docker run to check version, binary path)
        ↓
6. docker push to container registry
```

### Security Layer Build

The security layer extends the base image with security plugins. The **build context is the project root** (to access `*-security-layer/` directories):

```bash
cd nodeskclaw-artifacts

# OpenClaw: build base first, then security
./build.sh openclaw --version 2026.3.13 --build-only
./build.sh openclaw --with-security --base-tag v2026.3.13 --build-only

# Nanobot: same pattern
./build.sh nanobot --version 0.1.4 --build-only
./build.sh nanobot --with-security --base-tag v0.1.4 --build-only
```

Security layer tag format: `v{VERSION}-sec` (e.g. `v2026.3.13-sec`).

---

## 3. Engine Build Details

### 3.1 OpenClaw

**Dockerfile key steps:**

1. `node:22-bookworm-slim` base image
2. apt install system dependencies: git, openssh-client, python3, jq, curl, etc.
3. pip install Python dependencies: requests, tos
4. `npm install -g openclaw@${VERSION} @nodeskai/genehub`
5. Pre-create `/root/.openclaw/` directory tree (agents, config, credentials, extensions, skills, etc.)
6. COPY config template `openclaw.json.template` and startup scripts
7. Write version marker to `/root/.openclaw-version`

**Build arguments:**

| Argument | Description | Default |
|----------|-------------|---------|
| `NODE_VERSION` | Node.js major version | `22` |
| `OPENCLAW_VERSION` | npm package version | `2026.3.13` |
| `IMAGE_VERSION` | Image tag | `v2026.3.13` |

**Security layer:** `Dockerfile.security` simply `FROM base` + COPY `openclaw-security-layer/` into the `extensions/` directory. OpenClaw natively supports auto-loading TypeScript plugins from extensions.

### 3.2 Nanobot

**Dockerfile key steps:**

1. `python:3.13-slim-bookworm` base image
2. apt install ca-certificates, curl, gettext-base
3. `pip install nanobot-ai==${VERSION}`
4. COPY and pip install `nodeskclaw-tunnel-bridge`
5. COPY config template `nanobot.yaml.template` and entrypoint script

**Build arguments:**

| Argument | Description | Default |
|----------|-------------|---------|
| `NANOBOT_VERSION` | PyPI package version | `0.1.4` |
| `IMAGE_VERSION` | Image tag | `v0.1.4` |

**Security layer:** `Dockerfile.security` FROM base + `pip install nanobot-security-layer/` + replaces CMD with `python -m nanobot_security_layer.startup` (monkey-patches before launching nanobot).

---

## 4. Container Startup Flow (OpenClaw Example)

### Init Container (K8s Deployment)

The init container runs `init-container.sh` before the main container starts, handling PVC data initialization:

```
PVC empty?
  ├── Yes → First deploy: copy /root/.openclaw template to PVC, write version marker
  └── No  → Read PVC version
              ├── Same version → Skip
              └── Different version → Lightweight upgrade:
                    ├── Update version marker
                    ├── Merge built-in plugins (preserve user-customized plugins)
                    ├── Create any new subdirectories added in the new version
                    └── Update shell config files
```

### Main Container Startup (docker-entrypoint.sh)

```
1. Config initialization
   ├── OPENCLAW_FORCE_RECONFIG=true → Regenerate openclaw.json from template
   ├── Config file missing → First boot, generate from template
   └── Config file exists → Skip
       ↓
2. Config backfill (backward compatibility with older PVCs)
   └── Check and add missing controlUi fields
       ↓
3. Credential injection
   └── OPENCLAW_CREDENTIALS_JSON → Write to credentials/default.json
       ↓
4. Clear jiti compilation cache
       ↓
5. exec openclaw gateway (foreground, PID 1 receives SIGTERM)
```

### Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENCLAW_GATEWAY_PORT` | Gateway listen port | `18789` |
| `OPENCLAW_GATEWAY_BIND` | Bind strategy (`lan` = 0.0.0.0) | `lan` |
| `OPENCLAW_GATEWAY_TOKEN` | Auth token (auto-generated if unset) | Required |
| `OPENCLAW_LOG_LEVEL` | Log level | `info` |
| `OPENCLAW_FORCE_RECONFIG` | Set `true` to force config regeneration | `false` |
| `OPENCLAW_CREDENTIALS_JSON` | JSON credentials, written to credentials/ | Optional |
| `OPENAI_API_KEY` | OpenAI model key | Optional |
| `ANTHROPIC_API_KEY` | Anthropic model key | Optional |
| `SECURITY_LAYER_ENABLED` | Security layer toggle (preset `true` in security images) | `false` |

---

## 5. Version Management

### Manual Update Check

Each engine directory contains a `check-update.sh` script:

```bash
# Check for new versions
cd nodeskclaw-artifacts/openclaw-image && ./check-update.sh

# Check and auto-update Dockerfile version
./check-update.sh --update
```

Version detection logic per engine:

| Engine | Source | Stable Version Filter |
|--------|--------|-----------------------|
| OpenClaw | `npm view openclaw versions` | `YYYY.M.DD` format, excludes `-beta`, `-rc` suffixes |
| Nanobot | PyPI JSON API | `X.Y.Z` format, excludes pre-releases |

### Automated Version Detection (GitHub Actions)

`.github/workflows/check-runtime-updates.yml` defines a scheduled workflow:

- **Schedule**: Daily at UTC 08:00 (16:00 Beijing Time)
- **Behavior**: Three engines run as independent parallel jobs
- **On new version**: Auto-updates Dockerfile version ARGs and creates a PR
- **After PR merge**: Manually run `./build.sh` to build and push

```
Scheduled trigger → Read Dockerfile current version → Query upstream latest → Different?
    ├── No  → Done
    └── Yes → Update Dockerfile → Create PR (chore/{engine}-{version})
                                       ↓
                                Review & merge
                                       ↓
                                Manually run ./build.sh to build & push
```

---

## 6. `build.sh` Full Parameter Reference

```
./build.sh <engine> [options]
```

| Parameter | Description | Example |
|-----------|-------------|---------|
| `<engine>` | Engine name | `openclaw` / `nanobot` / `all` |
| `--version <ver>` | Specify version (auto-detect if omitted) | `--version 2026.3.13` |
| `--build-only` | Build only, skip push | |
| `--skip-verify` | Skip post-build verification | |
| `--with-security` | Build security layer image (requires `--base-tag`) | |
| `--base-tag <tag>` | Base image tag for security layer | `--base-tag v2026.3.13` |

### Image Registry Naming

| Engine | Full Image Name |
|--------|----------------|
| OpenClaw | `{REGISTRY_HOST}/{NAMESPACE}/deskclaw-openclaw:{tag}` |
| Nanobot | `{REGISTRY_HOST}/{NAMESPACE}/deskclaw-nanobot:{tag}` |

Tag format: Base layer `v{version}`, Security layer `v{version}-sec`.

---

## 7. Post-Build Verification

`build.sh` runs container verification by default (skip with `--skip-verify`):

```bash
# OpenClaw
docker run --rm <image> node --version          # Node.js version
docker run --rm <image> openclaw --version       # OpenClaw version
docker run --rm <image> cat /root/.openclaw-version  # Version marker
docker run --rm <image> ls /root/.openclaw/      # Directory structure

# Nanobot
docker run --rm <image> python --version
docker run --rm <image> pip show nanobot-ai      # Package version
```

---

## 8. Directory Structure Reference

```
nodeskclaw-artifacts/
├── build.sh                         # Unified build entry point
├── common.sh                        # Shared functions (registry config, docker_build wrapper)
├── openclaw-image/
│   ├── Dockerfile                   # Base image
│   ├── Dockerfile.security          # Security layer image
│   ├── docker-entrypoint.sh         # Container startup script
│   ├── init-container.sh            # K8s Init Container
│   ├── openclaw.json.template       # Config template (envsubst)
│   └── check-update.sh             # npm version detection
└── nanobot-image/
    ├── Dockerfile                   # Base: pip install
    ├── Dockerfile.security          # Security: pip install + CMD wrapper
    ├── nanobot.yaml.template        # Config template
    ├── docker-entrypoint.sh
    ├── check-update.sh             # PyPI version detection
    └── README.md
```

---

## 9. Troubleshooting

### Slow builds on Apple Silicon

The script forces `--platform linux/amd64` for cross-compilation. QEMU emulation of x86_64 significantly slows down builds. Recommendations:
- Use `--skip-verify` to skip the verification step (which launches an amd64 container)

### npm install fails during build

Check proxy settings. `docker_build` in `common.sh` explicitly clears all proxy environment variables (`http_proxy`, `https_proxy`, `HTTP_PROXY`, `HTTPS_PROXY`) to ensure direct npm registry access inside the container.

### Version not found

OpenClaw verifies version existence on npm before building. If this fails:
- Check version format (`YYYY.M.DD`, no `v` prefix)
- Manually verify with `npm view openclaw@{version} version`

### Push to registry fails

Make sure you are logged in to the target OCI registry:

```bash
docker login {REGISTRY_HOST}
```
