import type { ResolvedWecomAccount } from "./types.js";

type TokenCache = {
  token: string;
  expiresAt: number;
};

const tokenCache = new Map<string, TokenCache>();

async function fetchAccessToken(account: ResolvedWecomAccount): Promise<string> {
  const key = `${account.corpId}:${account.agentId}`;
  const now = Date.now();
  const cached = tokenCache.get(key);
  if (cached && cached.expiresAt > now + 15_000) {
    return cached.token;
  }

  const resp = await fetch("https://qyapi.weixin.qq.com/cgi-bin/gettoken", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      corpid: account.corpId,
      corpsecret: account.agentSecret,
    }),
  });
  if (!resp.ok) {
    throw new Error(`wecom gettoken failed: ${resp.status}`);
  }
  const payload = await resp.json() as { errcode?: number; errmsg?: string; access_token?: string; expires_in?: number };
  if (payload.errcode !== 0 || !payload.access_token) {
    throw new Error(`wecom gettoken error: ${payload.errmsg ?? "unknown"}`);
  }
  tokenCache.set(key, {
    token: payload.access_token,
    expiresAt: now + (payload.expires_in ?? 7200) * 1000,
  });
  return payload.access_token;
}

export async function sendTextMessage(
  account: ResolvedWecomAccount,
  to: string,
  text: string,
): Promise<{ ok: boolean; channelMessageId?: string; raw?: unknown; error?: string }> {
  const token = await fetchAccessToken(account);
  const touser = to || account.bindUserId || account.bindOpenUserId;
  if (!touser) {
    return { ok: false, error: "wecom target missing" };
  }

  const resp = await fetch(`https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=${encodeURIComponent(token)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      touser,
      msgtype: "text",
      agentid: Number(account.agentId),
      text: { content: text },
      safe: 0,
    }),
  });
  const payload = await resp.json() as { errcode?: number; errmsg?: string; msgid?: string };
  if (!resp.ok || payload.errcode !== 0) {
    return {
      ok: false,
      error: payload.errmsg || `wecom send failed: ${resp.status}`,
      raw: payload,
    };
  }
  return {
    ok: true,
    channelMessageId: payload.msgid || "",
    raw: payload,
  };
}
