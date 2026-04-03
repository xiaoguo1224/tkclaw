import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { nodeskclawPlugin } from "./src/channel.js";
import { setNoDeskClawRuntime } from "./src/runtime.js";
import { createNoDeskClawTools, NODESKCLAW_TOOL_NAMES } from "./src/tools.js";

const WORKSPACE_SESSION_PREFIX = "workspace:";

function extractWorkspaceId(sessionKey?: string): string | undefined {
  if (!sessionKey?.startsWith(WORKSPACE_SESSION_PREFIX)) return undefined;
  const raw = sessionKey.slice(WORKSPACE_SESSION_PREFIX.length);
  const separatorIndex = raw.indexOf(";");
  return separatorIndex >= 0 ? raw.slice(0, separatorIndex) : raw;
}

const plugin = {
  id: "nodeskclaw",
  name: "NoDeskClaw",
  description: "DeskClaw cyber office agent collaboration channel",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setNoDeskClawRuntime(api.runtime);
    api.registerChannel({ plugin: nodeskclawPlugin });

    api.registerTool((ctx: { sessionKey?: string }) => {
      const wsId = extractWorkspaceId(ctx.sessionKey);
      return createNoDeskClawTools(api.config, wsId);
    }, {
      optional: true,
      names: [...NODESKCLAW_TOOL_NAMES],
    });
  },
};

export default plugin;
