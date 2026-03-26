import type { ChannelPlugin, OpenClawConfig } from "openclaw/plugin-sdk";
import type { WecomAccountConfig, ResolvedWecomAccount } from "./types.js";
import { sendTextMessage } from "./send.js";
import { getWecomRuntime } from "./runtime.js";

const CHANNEL_KEY = "wecom";
const DEFAULT_ACCOUNT_ID = "default";

function getChannelSection(cfg: OpenClawConfig): Record<string, unknown> | undefined {
  return (cfg as Record<string, unknown>).channels?.[CHANNEL_KEY] as
    | Record<string, unknown>
    | undefined;
}

function resolveAccount(
  cfg: OpenClawConfig,
  accountId?: string | null,
): ResolvedWecomAccount {
  const section = getChannelSection(cfg);
  const accounts = (section?.accounts ?? {}) as Record<string, WecomAccountConfig>;
  const id = accountId ?? DEFAULT_ACCOUNT_ID;
  const raw = accounts[id];

  if (!raw) {
    return {
      accountId: id,
      enabled: false,
      configured: false,
      corpId: "",
      agentId: "",
      agentSecret: "",
      callbackToken: "",
      callbackAesKey: "",
      callbackUrl: "",
      bindUserId: "",
      bindOpenUserId: "",
    };
  }

  return {
    accountId: id,
    enabled: raw.enabled !== false,
    configured: Boolean(raw.corpId && raw.agentId && raw.agentSecret),
    corpId: raw.corpId ?? "",
    agentId: raw.agentId ?? "",
    agentSecret: raw.agentSecret ?? "",
    callbackToken: raw.callbackToken ?? "",
    callbackAesKey: raw.callbackAesKey ?? "",
    callbackUrl: raw.callbackUrl ?? "",
    bindUserId: raw.bindUserId ?? "",
    bindOpenUserId: raw.bindOpenUserId ?? "",
  };
}

export { resolveAccount };

export const wecomPlugin: ChannelPlugin<ResolvedWecomAccount> = {
  id: CHANNEL_KEY,
  meta: {
    id: CHANNEL_KEY,
    label: "WeCom",
    selectionLabel: "WeCom (企业微信)",
    docsPath: "/channels/wecom",
    blurb: "WeCom enterprise messaging channel.",
    aliases: ["qywx", "wechat-work"],
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
    isConfigured: (account) => account.configured,
    isEnabled: (account) => account.enabled,
    describeAccount: (account) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
      bindUserId: account.bindUserId,
    }),
  },
  outbound: {
    deliveryMode: "direct",
    sendText: async ({ cfg, to, text, accountId }) => {
      const account = resolveAccount(cfg, accountId);
      const result = await sendTextMessage(account, to, text);

      getWecomRuntime().channel.activity.record({
        channel: CHANNEL_KEY,
        accountId: account.accountId,
        direction: "outbound",
      });

      return result;
    },
    sendMedia: async ({ cfg, to, text, mediaUrl, accountId }) => {
      const account = resolveAccount(cfg, accountId);
      const body = mediaUrl ? `${text || ""}\n${mediaUrl}`.trim() : (text || "");
      const result = await sendTextMessage(account, to, body);

      getWecomRuntime().channel.activity.record({
        channel: CHANNEL_KEY,
        accountId: account.accountId,
        direction: "outbound",
      });

      return result;
    },
  },
  status: {
    buildAccountSnapshot: ({ account }) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
      bindUserId: account.bindUserId,
    }),
  },
};
