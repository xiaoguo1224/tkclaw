#!/usr/bin/env bash
# ============================================================
# NoDeskClaw 统一部署 CLI
#
# 用法:
#   ./deploy/cli.sh <command> [target] [options]
#
# 命令:
#   deploy [target]     构建 + 部署（默认 all，默认 staging）
#   release <version>   打 git tag + 创建 GitHub Pre-release
#   promote <version>   staging 镜像 -> 生产
#   init                首次环境初始化
#
# 目标 (deploy 命令):
#   all       backend + admin + portal + proxy（默认）
#   backend   后端
#   admin     Admin 前端
#   portal    Portal 前端
#   proxy     LLM Proxy
#
# 选项:
#   --staging       staging 环境（默认，可省略）
#   --prod          生产环境（需交互确认）
#   --context CTX   覆盖默认 K8s 上下文
#   --build-only    仅构建+推送镜像
#   --deploy-only   仅更新 K8s（需 --tag）
#   --tag TAG       镜像标签（默认 YYYYMMDD-<git-hash>）
#   --skip-proxy    all 时跳过 proxy
#   --no-cache      不使用 Docker 缓存
#   --env-file FILE init 时指定 .env 文件
#
# 前置条件:
#   - deploy/.env.local 已配置 REGISTRY 和 KUBE_CONTEXT
#   - docker login 已完成
#   - gh CLI 已安装并认证（release 命令需要）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>"
KUBE_CONTEXT=""
STAGING_NS="nodeskclaw-staging"
PROD_NS="nodeskclaw-system"

[[ -f "$SCRIPT_DIR/.env.local" ]] && source "$SCRIPT_DIR/.env.local"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[NoDeskClaw]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()  { echo -e "${RED}[ERROR ]${NC} $*" >&2; }

confirm() {
  echo ""
  echo -e "${YELLOW}$1${NC}"
  read -r -p "继续? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || { log "已取消"; exit 0; }
}

# ── 组件配置 ───────────────────────────────────────────────

get_image_name() {
  case "$1" in
    backend) echo "nodeskclaw-backend" ;;
    admin)   echo "nodeskclaw-admin" ;;
    portal)  echo "nodeskclaw-portal" ;;
    proxy)   echo "nodeskclaw-llm-proxy" ;;
    *)       return 1 ;;
  esac
}

get_build_context() {
  case "$1" in
    backend) echo "$PROJECT_ROOT" ;;
    admin)   echo "$PROJECT_ROOT/ee/nodeskclaw-frontend" ;;
    portal)  echo "$PROJECT_ROOT/nodeskclaw-portal" ;;
    proxy)   echo "$PROJECT_ROOT/nodeskclaw-llm-proxy" ;;
    *)       return 1 ;;
  esac
}

get_dockerfile() {
  case "$1" in
    backend) echo "$PROJECT_ROOT/nodeskclaw-backend/Dockerfile" ;;
    admin)   echo "$PROJECT_ROOT/ee/nodeskclaw-frontend/Dockerfile" ;;
    portal)  echo "$PROJECT_ROOT/nodeskclaw-portal/Dockerfile" ;;
    proxy)   echo "$PROJECT_ROOT/nodeskclaw-llm-proxy/Dockerfile" ;;
    *)       return 1 ;;
  esac
}

get_k8s_deployment() {
  case "$1" in
    backend) echo "nodeskclaw-backend" ;;
    admin)   echo "nodeskclaw-admin" ;;
    portal)  echo "nodeskclaw-portal" ;;
    proxy)   echo "nodeskclaw-llm-proxy" ;;
    *)       return 1 ;;
  esac
}

get_k8s_container() {
  case "$1" in
    proxy) echo "llm-proxy" ;;
    *)     get_image_name "$1" ;;
  esac
}

# ── 工具函数 ───────────────────────────────────────────────

require_context() {
  if [[ -z "$KUBE_CONTEXT" ]]; then
    err "需要 K8s 操作但未配置上下文"
    echo ""
    echo "请在 deploy/.env.local 中设置 KUBE_CONTEXT，或使用 --context 参数"
    echo ""
    echo "可用上下文:"
    kubectl config get-contexts -o name 2>/dev/null | while read -r ctx; do echo "  $ctx"; done
    exit 1
  fi
}

require_gh() {
  if ! command -v gh &>/dev/null; then
    err "gh CLI 未安装。请运行: brew install gh"
    exit 1
  fi
  if ! gh auth status &>/dev/null; then
    err "gh CLI 未认证。请运行: gh auth login"
    exit 1
  fi
}

# ── 构建 & 推送 ──────────────────────────────────────────

build_and_push() {
  local component="$1"
  local image_name; image_name="$(get_image_name "$component")"
  local image="${REGISTRY}/${image_name}:${TAG}"
  local context; context="$(get_build_context "$component")"
  local dockerfile; dockerfile="$(get_dockerfile "$component")"
  local extra_args=""

  if [[ "$component" != "proxy" && -d "$PROJECT_ROOT/ee" ]]; then
    local ee_df
    ee_df="$(mktemp)"
    case "$component" in
      backend)
        cat "$dockerfile" > "$ee_df"
        echo 'COPY ee/ ./ee/' >> "$ee_df"
        dockerfile="$ee_df"
        ;;
      admin)
        if [[ ! -d "$PROJECT_ROOT/ee/nodeskclaw-frontend" ]]; then
          warn "[$component] ee/nodeskclaw-frontend 不存在，跳过 admin 构建"
          return 0
        fi
        ;;
      portal)
        cat > "$ee_df" <<EODF
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
COPY --from=ee frontend/portal/ /ee/frontend/portal/
ARG VITE_APP_VERSION=dev
ENV VITE_APP_VERSION=\$VITE_APP_VERSION
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
EODF
        dockerfile="$ee_df"
        extra_args="--build-context ee=$PROJECT_ROOT/ee"
        ;;
    esac
    log "[$component] 检测到 ee/ 目录，构建 EE 版镜像"
  elif [[ "$component" == "admin" && ! -d "$PROJECT_ROOT/ee" ]]; then
    warn "[$component] ee/ 目录不存在（CE 版本），跳过 admin 构建"
    return 0
  fi

  case "$component" in
    portal|admin)
      extra_args="$extra_args --build-arg VITE_APP_VERSION=${TAG}"
      ;;
  esac

  log "[$component] 构建镜像: $image"
  if ! docker build --platform linux/amd64 \
    $NO_CACHE \
    $extra_args \
    -f "$dockerfile" \
    --build-arg http_proxy= \
    --build-arg https_proxy= \
    --build-arg HTTP_PROXY= \
    --build-arg HTTPS_PROXY= \
    -t "$image" \
    "$context"; then
    err "[$component] 镜像构建失败"
    return 1
  fi

  log "[$component] 推送镜像..."
  if ! docker push "$image"; then
    err "[$component] 镜像推送失败"
    return 1
  fi

  ok "[$component] $image"
}

# ── K8s 部署 ─────────────────────────────────────────────

deploy_to_k8s() {
  local component="$1"
  local image_name; image_name="$(get_image_name "$component")"
  local image="${REGISTRY}/${image_name}:${TAG}"
  local deployment; deployment="$(get_k8s_deployment "$component")"
  local container; container="$(get_k8s_container "$component")"

  log "[$component] 更新 Deployment: $deployment -> $image (context: $KUBE_CONTEXT)"

  if ! $KUBECTL -n "$NAMESPACE" get deployment "$deployment" &>/dev/null; then
    warn "[$component] Deployment 不存在，执行首次部署..."
    if [[ "$component" == "proxy" ]]; then
      local proxy_dir="$PROJECT_ROOT/nodeskclaw-llm-proxy/deploy"
      [[ -f "$proxy_dir/deployment.yaml" ]] && \
        sed "s|<YOUR_REGISTRY>/<YOUR_NAMESPACE>|${REGISTRY}|g" "$proxy_dir/deployment.yaml" \
          | $KUBECTL -n "$NAMESPACE" apply -f -
      [[ -f "$proxy_dir/service.yaml" ]] && \
        $KUBECTL -n "$NAMESPACE" apply -f "$proxy_dir/service.yaml"
    else
      local manifest="$SCRIPT_DIR/k8s/${component}.yaml"
      [[ -f "$manifest" ]] && \
        sed "s|<YOUR_REGISTRY>/<YOUR_NAMESPACE>|${REGISTRY}|g" "$manifest" \
          | $KUBECTL -n "$NAMESPACE" apply -f -
    fi
  fi

  $KUBECTL -n "$NAMESPACE" set image "deployment/$deployment" "$container=$image"

  log "[$component] 等待滚动更新完成..."
  local timeout=180
  [[ "$component" == "proxy" ]] && timeout=120
  if $KUBECTL -n "$NAMESPACE" rollout status "deployment/$deployment" --timeout="${timeout}s"; then
    ok "[$component] 部署完成"
  else
    err "[$component] 部署超时，请检查 Pod 状态"
    $KUBECTL -n "$NAMESPACE" get pods -l "app=$deployment"
    return 1
  fi
}

# ── cmd: deploy ──────────────────────────────────────────

cmd_deploy() {
  if [[ "$BUILD_ONLY" != true ]]; then
    require_context
  fi

  local targets=()
  if [[ "$TARGET" == "all" ]]; then
    targets=(backend admin portal)
    [[ "$SKIP_PROXY" != true ]] && targets+=(proxy)
  else
    targets=("$TARGET")
  fi

  log "镜像标签: ${TAG}"
  log "目标组件: ${targets[*]}"
  log "Namespace: $NAMESPACE"
  [[ -n "$KUBE_CONTEXT" ]] && log "K8s 上下文: $KUBE_CONTEXT"
  echo ""

  for t in "${targets[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [[ "$DEPLOY_ONLY" != true ]]; then
      if ! build_and_push "$t"; then
        err "[$t] 构建失败，中止后续组件"
        exit 1
      fi
    fi

    if [[ "$BUILD_ONLY" != true ]]; then
      if ! deploy_to_k8s "$t"; then
        err "[$t] 部署失败，中止后续组件"
        exit 1
      fi
    fi
  done

  echo ""
  ok "全部完成（标签: ${TAG}${NAMESPACE:+, Namespace: ${NAMESPACE}}）"
}

# ── cmd: release ─────────────────────────────────────────

generate_changelog() {
  local version="$1"
  local tmpfile; tmpfile="$(mktemp)"
  local last_tag; last_tag="$(git -C "$PROJECT_ROOT" describe --tags --abbrev=0 2>/dev/null || echo '')"

  local range="HEAD"
  [[ -n "$last_tag" ]] && range="${last_tag}..HEAD"

  local feats="" fixes="" refactors="" others=""

  while IFS= read -r line; do
    if [[ "$line" =~ ^feat ]]; then
      feats+="- ${line}"$'\n'
    elif [[ "$line" =~ ^fix ]]; then
      fixes+="- ${line}"$'\n'
    elif [[ "$line" =~ ^refactor|^perf ]]; then
      refactors+="- ${line}"$'\n'
    elif [[ "$line" =~ ^chore|^docs|^style|^build|^test ]]; then
      others+="- ${line}"$'\n'
    else
      others+="- ${line}"$'\n'
    fi
  done < <(git -C "$PROJECT_ROOT" log "$range" --pretty=format:"%s" --no-merges)

  {
    echo "# ${version}"
    echo ""
    [[ -n "$feats" ]] && { echo "## New Features"; echo ""; echo "$feats"; }
    [[ -n "$fixes" ]] && { echo "## Bug Fixes"; echo ""; echo "$fixes"; }
    [[ -n "$refactors" ]] && { echo "## Refactoring & Performance"; echo ""; echo "$refactors"; }
    [[ -n "$others" ]] && { echo "## Other Changes"; echo ""; echo "$others"; }
    echo ""
    [[ -n "$last_tag" ]] && echo "**Full Changelog**: https://github.com/NoDeskAI/nodeskclaw/compare/${last_tag}...${version}"
  } > "$tmpfile"

  echo "$tmpfile"
}

cmd_release() {
  require_gh
  log "=== RELEASE: 构建镜像 + 创建 GitHub Release ${VERSION} ==="
  echo ""

  local targets=(backend admin portal)
  [[ "$SKIP_PROXY" != true ]] && targets+=(proxy)

  log "生成 changelog..."
  local notes_file; notes_file="$(generate_changelog "$VERSION")"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  cat "$notes_file"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  confirm "即将构建镜像（${targets[*]}）、创建 git tag ${VERSION} 并发布 GitHub Pre-release"

  log "构建并推送镜像（标签: ${TAG}）..."
  for t in "${targets[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if ! build_and_push "$t"; then
      err "[$t] 镜像构建失败，中止 release"
      exit 1
    fi
  done

  echo ""
  log "创建 git tag..."
  git -C "$PROJECT_ROOT" tag "$VERSION"
  git -C "$PROJECT_ROOT" push origin "$VERSION"

  log "创建 GitHub Pre-release..."
  gh release create "$VERSION" \
    --repo NoDeskAI/nodeskclaw \
    --prerelease \
    --title "$VERSION" \
    --notes-file "$notes_file"

  rm -f "$notes_file"

  echo ""
  ok "GitHub Pre-release 已创建: ${VERSION}"
  log "镜像已推送: ${REGISTRY}/*:${TAG}"
  log "验证地址: https://github.com/NoDeskAI/nodeskclaw/releases/tag/${VERSION}"
  log "准备好升级生产环境后，运行:"
  echo "  ./deploy/cli.sh promote ${VERSION}"
}

# ── cmd: promote ──────────────────────────────────────────

cmd_promote() {
  require_context
  NAMESPACE="$PROD_NS"
  TAG="$VERSION"

  log "=== PROMOTE: 将 ${VERSION} 部署到生产环境 ${PROD_NS} ==="
  echo ""

  confirm "即将将 ${VERSION} 部署到生产环境 ${PROD_NS}（集群: ${KUBE_CONTEXT}）"

  local targets=(backend admin portal)
  [[ "$SKIP_PROXY" != true ]] && targets+=(proxy)

  for t in "${targets[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if ! deploy_to_k8s "$t"; then
      err "[$t] 部署失败，中止后续组件"
      exit 1
    fi
  done

  log "更新 GitHub Release 为正式版..."
  if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
    gh release edit "$VERSION" --repo NoDeskAI/nodeskclaw --prerelease=false 2>/dev/null || \
      warn "无法更新 GitHub Release，请手动执行: gh release edit ${VERSION} --prerelease=false"
  else
    warn "gh CLI 不可用，请手动执行: gh release edit ${VERSION} --prerelease=false"
  fi

  echo ""
  ok "生产环境部署完成: ${VERSION} -> ${PROD_NS}"
}

# ── cmd: init ─────────────────────────────────────────────

cmd_init() {
  require_context

  local env_file="${ENV_FILE:-$PROJECT_ROOT/nodeskclaw-backend/.env}"

  if [[ ! -f "$env_file" ]]; then
    err "环境变量文件不存在: $env_file"
    echo "请复制 .env.example 并填写实际值:"
    echo "  cp nodeskclaw-backend/.env.example nodeskclaw-backend/.env"
    exit 1
  fi

  log "集群: $KUBE_CONTEXT"
  log "Namespace: $NAMESPACE"

  log "检查 Namespace: $NAMESPACE"
  if ! $KUBECTL get namespace "$NAMESPACE" &>/dev/null; then
    log "创建 Namespace..."
    $KUBECTL create namespace "$NAMESPACE"
  fi
  ok "Namespace $NAMESPACE 就绪"

  local clean_env; clean_env=$(mktemp)
  trap 'rm -f "$clean_env"' EXIT

  while IFS= read -r line; do
    stripped="${line%%#*}"
    stripped="$(printf '%s' "$stripped" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$stripped" || "$stripped" != *"="* ]] && continue
    echo "$stripped"
  done < "$env_file" > "$clean_env"

  if [[ ! -s "$clean_env" ]]; then
    err ".env 文件中没有有效的键值对"
    exit 1
  fi

  local env_count; env_count=$(wc -l < "$clean_env" | xargs)
  local secret_name="nodeskclaw-backend-env"

  log "从 $env_file 创建 Secret: $secret_name"
  $KUBECTL -n "$NAMESPACE" create secret generic "$secret_name" \
    --from-env-file="$clean_env" \
    --dry-run=client -o yaml | $KUBECTL apply -f -
  ok "Secret $secret_name 已创建/更新 ($env_count 个变量)"

  log "应用 K8s 部署清单（Deployment + Service）..."
  for f in backend.yaml admin.yaml portal.yaml; do
    if [[ -f "$SCRIPT_DIR/k8s/$f" ]]; then
      sed "s|<YOUR_REGISTRY>/<YOUR_NAMESPACE>|${REGISTRY}|g" "$SCRIPT_DIR/k8s/$f" \
        | $KUBECTL -n "$NAMESPACE" apply -f -
      ok "$f"
    fi
  done
  log "Ingress 需要单独配置域名后手动 apply:"
  log "  kubectl --context $KUBE_CONTEXT -n $NAMESPACE apply -f $SCRIPT_DIR/k8s/ingress.yaml"

  echo ""
  log "初始化完成。接下来运行部署:"
  echo ""
  echo "  ./deploy/cli.sh deploy"
  echo ""
  log "当前 Deployment 状态:"
  $KUBECTL -n "$NAMESPACE" get deployments \
    -l 'app in (nodeskclaw-backend, nodeskclaw-admin, nodeskclaw-portal)' 2>/dev/null || true
}

# ── 参数解析 ─────────────────────────────────────────────

usage() {
  cat <<EOF
用法: $0 <command> [target] [options]

命令:
  deploy [target]     构建 + 部署（默认 all，默认 staging）
  release <version>   打 git tag + 创建 GitHub Pre-release
  promote <version>   staging 镜像 -> 生产
  init                首次环境初始化

目标 (deploy 命令):
  all       backend + admin + portal + proxy（默认）
  backend   后端
  admin     Admin 前端
  portal    Portal 前端
  proxy     LLM Proxy

选项:
  --staging       staging 环境（默认，可省略）
  --prod          生产环境（需交互确认）
  --context CTX   覆盖默认 K8s 上下文
  --build-only    仅构建+推送镜像
  --deploy-only   仅更新 K8s（需 --tag）
  --tag TAG       镜像标签（默认 YYYYMMDD-<git-hash>）
  --skip-proxy    all 时跳过 proxy
  --no-cache      不使用 Docker 缓存
  --env-file FILE init 时指定 .env 文件
EOF
  exit 1
}

[[ $# -lt 1 ]] && usage

COMMAND="$1"; shift

TARGET="all"
VERSION=""
CUSTOM_TAG=""
BUILD_ONLY=false
DEPLOY_ONLY=false
NO_CACHE=""
SKIP_PROXY=false
ENV_FILE=""
IS_PROD=false

case "$COMMAND" in
  deploy)
    if [[ $# -gt 0 && ! "$1" =~ ^-- ]]; then
      TARGET="$1"
      if [[ "$TARGET" != "all" ]] && ! get_image_name "$TARGET" >/dev/null 2>&1; then
        err "未知目标: $TARGET"
        usage
      fi
      shift
    fi
    ;;
  release|promote)
    if [[ $# -lt 1 ]]; then
      err "$COMMAND 命令需要 version 参数"
      usage
    fi
    VERSION="$1"; shift
    ;;
  init) ;;
  *)
    err "未知命令: $COMMAND"
    usage
    ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --context)     KUBE_CONTEXT="$2"; shift ;;
    --staging)     IS_PROD=false ;;
    --prod)        IS_PROD=true ;;
    --build-only)  BUILD_ONLY=true ;;
    --deploy-only) DEPLOY_ONLY=true ;;
    --tag)         CUSTOM_TAG="$2"; shift ;;
    --skip-proxy)  SKIP_PROXY=true ;;
    --no-cache)    NO_CACHE="--no-cache" ;;
    --env-file)    ENV_FILE="$2"; shift ;;
    *)             err "未知参数: $1"; usage ;;
  esac
  shift
done

if [[ "$IS_PROD" == true ]]; then
  NAMESPACE="$PROD_NS"
  [[ "$COMMAND" == "deploy" ]] && confirm "即将部署到生产环境 ${PROD_NS}"
else
  NAMESPACE="$STAGING_NS"
fi

if [[ -n "$CUSTOM_TAG" ]]; then
  TAG="$CUSTOM_TAG"
elif [[ -n "$VERSION" ]]; then
  TAG="$VERSION"
else
  TAG="$(date +%Y%m%d)-$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'manual')"
fi

if [[ "$BUILD_ONLY" == true && "$DEPLOY_ONLY" == true ]]; then
  err "--build-only 和 --deploy-only 不能同时使用"
  exit 1
fi

if [[ "$DEPLOY_ONLY" == true && -z "$CUSTOM_TAG" && -z "$VERSION" ]]; then
  err "--deploy-only 需要通过 --tag 指定镜像标签"
  exit 1
fi

KUBECTL="kubectl"
[[ -n "$KUBE_CONTEXT" ]] && KUBECTL="kubectl --context $KUBE_CONTEXT"

case "$COMMAND" in
  deploy)  cmd_deploy ;;
  release) cmd_release ;;
  promote) cmd_promote ;;
  init)    cmd_init ;;
esac
