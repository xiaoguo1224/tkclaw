import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { nodeskclawPlugin } from "./src/channel.js";
import { setNoDeskClawRuntime } from "./src/runtime.js";
import { createNoDeskClawTools, NODESKCLAW_TOOL_NAMES } from "./src/tools.js";

const WORKSPACE_SESSION_PREFIX = "workspace:";

const plugin = {
  id: "nodeskclaw",
  name: "NoDeskClaw",
  description: "DeskClaw cyber office agent collaboration channel",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setNoDeskClawRuntime(api.runtime);
    api.registerChannel({ plugin: nodeskclawPlugin });

    api.registerTool((ctx: { sessionKey?: string }) => {
      const wsId = ctx.sessionKey?.startsWith(WORKSPACE_SESSION_PREFIX)
        ? ctx.sessionKey.slice(WORKSPACE_SESSION_PREFIX.length)
        : undefined;
      return createNoDeskClawTools(api.config, wsId);
    }, {
      optional: true,
      names: [...NODESKCLAW_TOOL_NAMES],
    });
  },
};

export default plugin;
