#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${BUNDLED_EXTENSIONS_SOURCE_DIR:-/opt/openclaw-bundled-extensions}"
TARGET_DIR="${1:-/root/.openclaw/extensions}"

if [ ! -d "${SOURCE_DIR}" ]; then
  echo "[sync-extensions] 未找到内置插件目录: ${SOURCE_DIR}，跳过同步"
  exit 0
fi

mkdir -p "${TARGET_DIR}"

added=0
skipped=0

for ext_dir in "${SOURCE_DIR}"/*; do
  if [ ! -d "${ext_dir}" ]; then
    continue
  fi
  ext_name=$(basename "${ext_dir}")
  target="${TARGET_DIR}/${ext_name}"
  if [ ! -e "${target}" ]; then
    cp -a "${ext_dir}" "${target}"
    echo "[sync-extensions] 已同步内置插件: ${ext_name}"
    added=$((added + 1))
  else
    echo "[sync-extensions] 插件已存在，跳过: ${ext_name}"
    skipped=$((skipped + 1))
  fi
done

echo "[sync-extensions] 同步完成: 新增 ${added}，跳过 ${skipped}"
