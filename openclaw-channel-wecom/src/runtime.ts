import type { PluginRuntime } from "openclaw/plugin-sdk";

let runtime: PluginRuntime | null = null;

export function setWecomRuntime(next: PluginRuntime) {
  runtime = next;
}

export function getWecomRuntime(): PluginRuntime {
  if (!runtime) {
    throw new Error("WeCom runtime not initialized");
  }
  return runtime;
}
