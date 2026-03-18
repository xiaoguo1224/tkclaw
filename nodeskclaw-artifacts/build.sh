#!/bin/bash
# build.sh — DeskClaw 统一镜像构建入口
#
# 用法:
#   ./build.sh <engine> --version <ver> [--build-only] [--skip-verify] [--with-security --base-tag <tag>]
#
# 示例:
#   ./build.sh openclaw --version 2026.3.13
#   ./build.sh zeroclaw --version v0.1.0 --build-only
#   ./build.sh nanobot --version 0.1.4
#   ./build.sh openclaw --with-security --base-tag v2026.3.13
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ENGINE="$1"; shift || true
if [ -z "${ENGINE}" ]; then
  log_error "用法: ./build.sh <engine> --version <ver> [--build-only] [--with-security --base-tag <tag>]"
  log_info "可用引擎: openclaw, zeroclaw, nanobot"
  exit 1
fi

ENGINE_DIR="${SCRIPT_DIR}/${ENGINE}-image"
if [ ! -d "${ENGINE_DIR}" ]; then
  log_error "引擎目录不存在: ${ENGINE_DIR}"
  exit 1
fi

check_docker
parse_common_args "$@"

REGISTRY="$(registry_for "${ENGINE}")"

# --- 版本号归一化：统一去掉用户输入的 v 前缀，tag 统一加 v ---
VERSION="${VERSION#v}"

# --- 安全层模式 ---
if [ "${WITH_SECURITY}" = true ]; then
  CONTEXT_DIR="${SCRIPT_DIR}/../"
  BASE_TAG="${BASE_TAG#v}"
  IMAGE_TAG="v${BASE_TAG}-sec"

  print_build_summary "${ENGINE} (security)" "${BASE_TAG}" "${REGISTRY}" "linux/amd64" "security"

  case "${ENGINE}" in
    zeroclaw)
      docker_build "${CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
        -f "${ENGINE_DIR}/Dockerfile.security" \
        --build-arg ZEROCLAW_REPO="${ZEROCLAW_REPO:-https://github.com/zeroclaw-labs/zeroclaw.git}" \
        --build-arg ZEROCLAW_REF="${ZEROCLAW_REF:-master}" \
        --build-arg IMAGE_VERSION="${IMAGE_TAG}"
      ;;
    *)
      docker_build "${CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
        -f "${ENGINE_DIR}/Dockerfile.security" \
        --build-arg BASE_TAG="v${BASE_TAG}" \
        --build-arg BASE_REGISTRY="${REGISTRY}"
      ;;
  esac
else
  # --- Base 模式 ---
  if [ -z "${VERSION}" ]; then
    if [ "${ENGINE}" = "openclaw" ]; then
      VERSION=$(sed -n 's/^ARG OPENCLAW_VERSION=//p' "${ENGINE_DIR}/Dockerfile")
    fi
    if [ -z "${VERSION}" ]; then
      log_error "必须通过 --version 指定版本"
      exit 1
    fi
    log_info "使用 Dockerfile 中的默认版本: ${VERSION}"
  fi

  if [ "${ENGINE}" = "openclaw" ]; then
    log_info "验证 openclaw@${VERSION} 在 npm 上是否存在..."
    NPM_INFO=$(npm view "openclaw@${VERSION}" version 2>/dev/null || true)
    if [ -z "${NPM_INFO}" ]; then
      log_error "openclaw@${VERSION} 在 npm 上不存在"
      echo "可用的最新版本:"
      npm view openclaw versions --json 2>/dev/null | tail -10
      exit 1
    fi
    log_success "openclaw@${VERSION} 存在"
  fi

  if [ -d "${SCRIPT_DIR}/../nodeskclaw-tunnel-bridge" ] && [ "${ENGINE}" != "openclaw" ]; then
    cp -r "${SCRIPT_DIR}/../nodeskclaw-tunnel-bridge" "${ENGINE_DIR}/nodeskclaw-tunnel-bridge"
    trap "rm -rf '${ENGINE_DIR}/nodeskclaw-tunnel-bridge'" EXIT
  fi

  IMAGE_TAG="v${VERSION}"

  case "${ENGINE}" in
    zeroclaw) BUILD_ARG_VERSION="v${VERSION}" ;;
    *)        BUILD_ARG_VERSION="${VERSION}" ;;
  esac

  print_build_summary "${ENGINE}" "${VERSION}" "${REGISTRY}" "linux/amd64" "base"

  ENGINE_UPPER="$(echo "${ENGINE}" | tr '[:lower:]' '[:upper:]')"

  docker_build "${ENGINE_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
    --build-arg "${ENGINE_UPPER}_VERSION=${BUILD_ARG_VERSION}" \
    --build-arg IMAGE_VERSION="${IMAGE_TAG}"
fi

# --- 验证（可选）---
if [ "${SKIP_VERIFY}" = false ] && [ "${WITH_SECURITY}" = false ]; then
  log_info "验证镜像（Apple Silicon 上较慢，可用 --skip-verify 跳过）..."
  case "${ENGINE}" in
    openclaw)
      echo "  Node.js: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" node --version)"
      echo "  OpenClaw: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" openclaw --version 2>/dev/null || echo '(需启动后验证)')"
      echo "  版本标记: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" cat /root/.openclaw-version)"
      ;;
    zeroclaw)
      echo "  ZeroClaw: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" zeroclaw --version 2>/dev/null || echo '(需启动后验证)')"
      ;;
    nanobot)
      echo "  Python: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" python --version)"
      echo "  Nanobot: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" pip show nanobot-ai 2>/dev/null | grep Version || echo '(需启动后验证)')"
      ;;
  esac
fi

# --- 推送 ---
log_success "构建完成"

if [ "${BUILD_ONLY}" = true ]; then
  log_info "仅构建模式，跳过推送"
  echo "如需推送，运行: docker push ${REGISTRY}:${IMAGE_TAG}"
  exit 0
fi

docker_push "${REGISTRY}:${IMAGE_TAG}"
print_done "${REGISTRY}:${IMAGE_TAG}"
