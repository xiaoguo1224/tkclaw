#!/usr/bin/env npx ts-node
/**
 * NoDeskClaw Performance Reader MCP Server
 * Lets agents read their own and team performance metrics.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const API = process.env.NODESKCLAW_API_URL || "http://localhost:4510/api/v1";
const TOKEN = process.env.NODESKCLAW_TOKEN || "";
const WORKSPACE_ID = process.env.NODESKCLAW_WORKSPACE_ID || "";

async function apiFetch(path: string, method = "GET") {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { method, headers: { Authorization: `Bearer ${TOKEN}` } });
  } catch (err) {
    return { error: true, message: `Network error: ${(err as Error).message}` };
  }
  if (!res.ok) {
    let detail: string;
    try { detail = await res.text(); } catch { detail = ""; }
    return { error: true, status: res.status, message: detail || res.statusText };
  }
  try {
    return await res.json();
  } catch {
    return { error: true, message: "Response is not valid JSON" };
  }
}

const server = new Server({ name: "nodeskclaw-performance-reader", version: "1.0.0" }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    { name: "get_my_performance", description: "Read my own performance metrics from the blackboard", inputSchema: { type: "object", properties: { my_instance_id: { type: "string" } }, required: ["my_instance_id"] } },
    { name: "get_team_performance", description: "Read all team members' performance for comparison", inputSchema: { type: "object", properties: {} } },
    { name: "collect_performance", description: "Trigger a fresh performance data collection", inputSchema: { type: "object", properties: {} } },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  const ws = WORKSPACE_ID;
  let result: unknown;

  switch (name) {
    case "get_my_performance": {
      const bb = await apiFetch(`/workspaces/${ws}/blackboard`);
      const perf = (bb.data?.performance || []) as any[];
      result = perf.find((p: any) => p.member_id === (args as any).my_instance_id) || { error: "No data found" };
      break;
    }
    case "get_team_performance": {
      const bb = await apiFetch(`/workspaces/${ws}/blackboard`);
      result = bb.data?.performance || [];
      break;
    }
    case "collect_performance":
      result = await apiFetch(`/workspaces/${ws}/blackboard/performance/collect`, "POST");
      break;
    default:
      return { content: [{ type: "text", text: `Unknown tool: ${name}` }] };
  }
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

const transport = new StdioServerTransport();
server.connect(transport);
