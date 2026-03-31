#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const openclawDir = process.env.OPENCLAW_DIR || "/root/.openclaw";
const sessionsDir = path.join(openclawDir, "agents", "main", "sessions");
const sessionsFile = path.join(sessionsDir, "sessions.json");
const sessionFilePrefix = "/root/.openclaw/agents/main/sessions";

function deriveSessionKey(stem) {
  if (stem.startsWith("agent_main_")) {
    return `agent:main:${stem.slice("agent_main_".length)}`;
  }
  return `agent:main:${stem}`;
}

function loadStore() {
  if (!fs.existsSync(sessionsFile)) {
    return {};
  }

  try {
    const raw = fs.readFileSync(sessionsFile, "utf8");
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch (error) {
    console.warn(`[entrypoint] sessions.json 解析失败，跳过会话索引修复: ${error.message}`);
  }

  return null;
}

function main() {
  if (!fs.existsSync(sessionsDir)) {
    return;
  }

  const store = loadStore();
  if (store === null) {
    return;
  }

  const files = fs.readdirSync(sessionsDir)
    .filter((name) => name.endsWith(".jsonl"))
    .sort();
  const knownFiles = new Set(files.map((file) => `${sessionFilePrefix}/${file}`));

  let changed = false;

  for (const [key, value] of Object.entries(store)) {
    if (!value || typeof value !== "object") {
      continue;
    }

    const sessionFile = value.sessionFile;
    if (typeof sessionFile !== "string" || !sessionFile.startsWith(sessionFilePrefix)) {
      continue;
    }

    if (knownFiles.has(sessionFile)) {
      continue;
    }

    delete store[key];
    changed = true;
  }

  for (const file of files) {
    const stem = path.basename(file, ".jsonl");
    const key = deriveSessionKey(stem);
    const absoluteSessionFile = `${sessionFilePrefix}/${file}`;
    const existing = store[key];

    if (
      existing &&
      typeof existing === "object" &&
      existing.sessionId === stem &&
      existing.sessionFile === absoluteSessionFile
    ) {
      continue;
    }

    store[key] = {
      ...(existing && typeof existing === "object" ? existing : {}),
      sessionId: stem,
      sessionFile: absoluteSessionFile,
    };
    changed = true;
  }

  if (!changed) {
    return;
  }

  fs.writeFileSync(sessionsFile, `${JSON.stringify(store, null, 2)}\n`, "utf8");
  console.log(`[entrypoint] 已修复会话索引: ${files.length} 个会话文件已扫描`);
}

main();
