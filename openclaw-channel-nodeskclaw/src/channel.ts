import type { ChannelPlugin, OpenClawConfig } from "openclaw/plugin-sdk";
import type {
  NoDeskClawAccountConfig,
  ResolvedNoDeskClawAccount,
  CollaborationPayload,
} from "./types.js";
import { getNoDeskClawRuntime } from "./runtime.js";
import { broadcast } from "./sse-server.js";

const CHANNEL_KEY = "nodeskclaw";
const DEFAULT_ACCOUNT_ID = "default";

function getChannelSection(cfg: OpenClawConfig): Record<string, unknown> | undefined {
  return (cfg as Record<string, unknown>).channels?.[CHANNEL_KEY] as
    | Record<string, unknown>
    | undefined;
}

function resolveAccount(
  cfg: OpenClawConfig,
  accountId?: string | null,
): ResolvedNoDeskClawAccount {
  const section = getChannelSection(cfg);
  const accounts = (section?.accounts ?? {}) as Record<string, NoDeskClawAccountConfig>;
  const id = accountId ?? DEFAULT_ACCOUNT_ID;
  const raw = accounts[id];

  if (!raw) {
    return {
      accountId: id,
      enabled: false,
      configured: false,
      apiUrl: "",
      workspaceId: "",
      instanceId: "",
      apiToken: "",
    };
  }

  return {
    accountId: id,
    enabled: raw.enabled !== false,
    configured: Boolean(raw.workspaceId && raw.instanceId),
    apiUrl: raw.apiUrl ?? "",
    workspaceId: raw.workspaceId ?? "",
    instanceId: raw.instanceId ?? "",
    apiToken: raw.apiToken ?? "",
  };
}

async function listNoDeskClawPeers(params: {
  cfg: OpenClawConfig;
  accountId?: string | null;
  query?: string | null;
  limit?: number | null;
  runtime?: unknown;
}): Promise<Array<{ kind: "user"; id: string; name: string }>> {
  const account = resolveAccount(params.cfg, params.accountId);
  if (!account.configured || !account.apiUrl) return [];
  try {
    const url = `${account.apiUrl}/workspaces/${account.workspaceId}/topology/reachable?instance_id=${account.instanceId}`;
    const resp = await fetch(url, {
      headers: { "X-Proxy-Token": account.apiToken },
    });
    if (!resp.ok) return [];
    const body = await resp.json();
    const reachable: Array<{ type: string; entity_id: string; display_name?: string }> =
      body?.data?.reachable || [];
    const q = (params.query ?? "").toLowerCase();
    let entries = reachable
      .filter((ep) => ep.type === "agent" || ep.type === "human")
      .map((ep) => ({
        kind: "user" as const,
        id: ep.type === "agent" ? `agent:${ep.display_name}` : `human:${ep.entity_id}`,
        name: ep.display_name || ep.entity_id,
      }));
    if (q) entries = entries.filter((e) => e.name.toLowerCase().includes(q));
    if (params.limit && params.limit > 0) entries = entries.slice(0, params.limit);
    return entries;
  } catch {
    return [];
  }
}

export const nodeskclawPlugin: ChannelPlugin<ResolvedNoDeskClawAccount> = {
  id: CHANNEL_KEY,
  meta: {
    id: CHANNEL_KEY,
    label: "NoDeskClaw",
    selectionLabel: "DeskClaw (Cyber Office)",
    docsPath: "/channels/nodeskclaw",
    blurb: "DeskClaw cyber office AI employee collaboration channel.",
    aliases: ["cb"],
  },
  capabilities: {
    chatTypes: ["direct"],
  },
  config: {
    listAccountIds: (cfg) => {
      const section = getChannelSection(cfg);
      return Object.keys((section?.accounts ?? {}) as Record<string, unknown>);
    },
    resolveAccount: (cfg, accountId) => resolveAccount(cfg, accountId),
    isConfigured: (account, _cfg) => account.configured,
    isEnabled: (account, _cfg) => account.enabled,
    describeAccount: (account, _cfg) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
    }),
  },
  outbound: {
    deliveryMode: "direct",
    sendText: async ({ cfg, to, text, accountId }) => {
      const account = resolveAccount(cfg, accountId);

      const payload: CollaborationPayload = {
        workspace_id: account.workspaceId,
        source_instance_id: account.instanceId,
        target: to,
        text,
        depth: 0,
      };

      broadcast(payload);

      getNoDeskClawRuntime().channel.activity.record({
        channel: CHANNEL_KEY,
        accountId: account.accountId,
        direction: "outbound",
      });

      const messageId = `cb-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      return { channel: CHANNEL_KEY, messageId };
    },
    sendMedia: async ({ cfg, to, text, mediaUrl, accountId }) => {
      const account = resolveAccount(cfg, accountId);
      const body = mediaUrl ? `${text || ""}\n[${mediaUrl}]`.trim() : (text || "");

      const payload: CollaborationPayload = {
        workspace_id: account.workspaceId,
        source_instance_id: account.instanceId,
        target: to,
        text: body,
        depth: 0,
      };

      broadcast(payload);

      getNoDeskClawRuntime().channel.activity.record({
        channel: CHANNEL_KEY,
        accountId: account.accountId,
        direction: "outbound",
      });

      const messageId = `cb-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      return { channel: CHANNEL_KEY, messageId };
    },
  },
  directory: {
    listPeers: (params) => listNoDeskClawPeers(params),
    listPeersLive: (params) => listNoDeskClawPeers(params),
  },
  messaging: {
    normalizeTarget: (raw: string) => {
      const trimmed = raw.trim();
      if (!trimmed) return undefined;
      if (/^(agent|human):/.test(trimmed) || trimmed === "broadcast") return trimmed;
      return `agent:${trimmed}`;
    },
    targetResolver: {
      looksLikeId: (raw: string, normalized?: string) => {
        const check = (s: string) => /^(agent|human):/.test(s) || s === "broadcast";
        return check(raw) || (normalized ? check(normalized) : false);
      },
      hint: "agent:{name} | human:{hex_id} | broadcast",
    },
  },
  agentPrompt: {
    messageToolHints: () => [
      `Use "send -t nodeskclaw -to \\"agent:{name}\\" -m \\"message\\"" to collaborate with other AI employees.`,
      `IMPORTANT: You can ONLY message agents/humans reachable from your hex position via corridor connections. Before claiming you can contact someone, call get_my_neighbors to check. If an agent is not in the result, you CANNOT message them.`,
      `If you are in multiple workspaces, add accountId=<workspace_account_id> to specify which workspace to send from.`,
      `If get_my_neighbors returns a blackboard (node_type=blackboard), you can interact with it via the nodeskclaw_blackboard tool. The blackboard is for shared tasks and objectives — do NOT use send to message it.`,
    ],
  },
  status: {
    buildAccountSnapshot: ({ account }) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
    }),
  },
};
