export type WecomAccountConfig = {
  corpId: string;
  agentId: string;
  agentSecret: string;
  callbackToken?: string;
  callbackAesKey?: string;
  callbackUrl?: string;
  bindUserId?: string;
  bindOpenUserId?: string;
  enabled?: boolean;
};

export type ResolvedWecomAccount = {
  accountId: string;
  enabled: boolean;
  configured: boolean;
  corpId: string;
  agentId: string;
  agentSecret: string;
  callbackToken: string;
  callbackAesKey: string;
  callbackUrl: string;
  bindUserId: string;
  bindOpenUserId: string;
};
