import type { SessionWebhookEntry, ResolvedDingTalkAccount } from "./types.js";

const DINGTALK_API = "https://api.dingtalk.com";
const TOKEN_CACHE_SAFETY_MARGIN_MS = 5 * 60 * 1000;

const webhookStore = new Map<string, SessionWebhookEntry>();

let cachedToken: { token: string; expiresAt: number } | null = null;

export function storeSessionWebhook(entry: SessionWebhookEntry): void {
  const key = `${entry.conversationId}:${entry.senderStaffId}`;
  webhookStore.set(key, entry);
}

function getSessionWebhook(conversationId: string, staffId: string): string | null {
  const key = `${conversationId}:${staffId}`;
  const entry = webhookStore.get(key);
  if (!entry) return null;

  if (Date.now() >= entry.expiredTime) {
    webhookStore.delete(key);
    return null;
  }

  return entry.webhook;
}

async function getAccessToken(account: ResolvedDingTalkAccount): Promise<string> {
  if (cachedToken && Date.now() < cachedToken.expiresAt) {
    return cachedToken.token;
  }

  const resp = await fetch(`${DINGTALK_API}/v1.0/oauth2/accessToken`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      appKey: account.clientId,
      appSecret: account.clientSecret,
    }),
  });

  if (!resp.ok) {
    throw new Error(`DingTalk accessToken failed: ${resp.status}`);
  }

  const body = (await resp.json()) as { accessToken: string; expireIn: number };
  const ttlMs = (body.expireIn > 0 ? body.expireIn : 7200) * 1000 - TOKEN_CACHE_SAFETY_MARGIN_MS;
  cachedToken = {
    token: body.accessToken,
    expiresAt: Date.now() + Math.max(ttlMs, 60_000),
  };

  return body.accessToken;
}

async function sendViaWebhook(webhook: string, content: string, msgType: "text" | "markdown" = "text"): Promise<boolean> {
  const body = msgType === "markdown"
    ? { msgtype: "markdown", markdown: { title: "Reply", text: content } }
    : { msgtype: "text", text: { content } };

  const resp = await fetch(webhook, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  return resp.ok;
}

async function sendViaRobotApi(
  account: ResolvedDingTalkAccount,
  staffId: string,
  content: string,
  msgType: "text" | "markdown" = "text",
): Promise<boolean> {
  const token = await getAccessToken(account);
  const robotCode = account.robotCode || account.clientId;

  const msgParam = msgType === "markdown"
    ? JSON.stringify({ title: "Reply", text: content })
    : JSON.stringify({ content });

  const msgKey = msgType === "markdown" ? "sampleMarkdown" : "sampleText";

  const resp = await fetch(`${DINGTALK_API}/v1.0/robot/oToMessages/batchSend`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-acs-dingtalk-access-token": token,
    },
    body: JSON.stringify({
      robotCode,
      userIds: [staffId],
      msgKey,
      msgParam,
    }),
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    console.error("[dingtalk-send] Robot API failed:", resp.status, text);
    return false;
  }

  return true;
}

export async function sendTextMessage(
  account: ResolvedDingTalkAccount,
  to: string,
  content: string,
): Promise<{ channel: string; messageId: string }> {
  const [conversationId, staffId] = parseTarget(to);

  if (conversationId && staffId) {
    const webhook = getSessionWebhook(conversationId, staffId);
    if (webhook) {
      const ok = await sendViaWebhook(webhook, content);
      if (ok) {
        return { channel: "dingtalk", messageId: `dt-wh-${Date.now()}` };
      }
    }
  }

  if (staffId) {
    const ok = await sendViaRobotApi(account, staffId, content);
    if (ok) {
      return { channel: "dingtalk", messageId: `dt-api-${Date.now()}` };
    }
  }

  throw new Error(`DingTalk send failed: no valid delivery path for target "${to}"`);
}

export async function sendMarkdownMessage(
  account: ResolvedDingTalkAccount,
  to: string,
  content: string,
): Promise<{ channel: string; messageId: string }> {
  const [conversationId, staffId] = parseTarget(to);

  if (conversationId && staffId) {
    const webhook = getSessionWebhook(conversationId, staffId);
    if (webhook) {
      const ok = await sendViaWebhook(webhook, content, "markdown");
      if (ok) {
        return { channel: "dingtalk", messageId: `dt-wh-${Date.now()}` };
      }
    }
  }

  if (staffId) {
    const ok = await sendViaRobotApi(account, staffId, content, "markdown");
    if (ok) {
      return { channel: "dingtalk", messageId: `dt-api-${Date.now()}` };
    }
  }

  throw new Error(`DingTalk markdown send failed for target "${to}"`);
}

function parseTarget(to: string): [string | null, string | null] {
  if (to.includes(":")) {
    const [conversationId, staffId] = to.split(":", 2);
    return [conversationId || null, staffId || null];
  }
  return [null, to || null];
}
