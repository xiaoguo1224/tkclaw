#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const openclawDir = process.env.OPENCLAW_DIR || "/root/.openclaw";
const memoryDir = path.join(openclawDir, "memory");
const skillsDir = path.join(openclawDir, "skills");
const legacyMemoryFile = path.join(memoryDir, "Claw_Smith_Memory.md");
const memoryFile = path.join(memoryDir, "MEMORY.md");
const legacySkillsDir = path.join(openclawDir, "workspace", "skills");

function migrateMemory() {
  if (!fs.existsSync(legacyMemoryFile)) {
    return false;
  }

  if (!fs.existsSync(memoryFile)) {
    fs.renameSync(legacyMemoryFile, memoryFile);
    console.log("[entrypoint] 已迁移旧记忆文件到 MEMORY.md");
    return true;
  }

  fs.rmSync(legacyMemoryFile, { force: true });
  console.log("[entrypoint] 已清理旧记忆文件 Claw_Smith_Memory.md");
  return true;
}

function migrateSkills() {
  if (!fs.existsSync(legacySkillsDir) || !fs.statSync(legacySkillsDir).isDirectory()) {
    return false;
  }

  fs.mkdirSync(skillsDir, { recursive: true });
  let movedCount = 0;

  for (const entry of fs.readdirSync(legacySkillsDir)) {
    const from = path.join(legacySkillsDir, entry);
    const to = path.join(skillsDir, entry);

    if (fs.existsSync(to)) {
      continue;
    }

    fs.renameSync(from, to);
    movedCount += 1;
  }

  if (movedCount === 0) {
    return false;
  }

  console.log(`[entrypoint] 已迁移 ${movedCount} 个旧技能目录到 /root/.openclaw/skills`);
  return true;
}

function main() {
  if (!fs.existsSync(openclawDir)) {
    return;
  }

  migrateMemory();
  migrateSkills();
}

main();
