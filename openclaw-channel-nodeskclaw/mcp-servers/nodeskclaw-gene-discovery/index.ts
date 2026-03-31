#!/usr/bin/env npx ts-node
/**
 * NoDeskClaw Gene Discovery MCP Server
 * Lets agents search the gene market, inspect gene details, and request learning.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const API = process.env.NODESKCLAW_API_URL || "http://localhost:4510/api/v1";
const TOKEN = process.env.NODESKCLAW_TOKEN || "";

async function apiFetch(path: string, method = "GET", body?: unknown) {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      method,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${TOKEN}` },
      body: body ? JSON.stringify(body) : undefined,
    });
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

const server = new Server({ name: "nodeskclaw-gene-discovery", version: "1.0.0" }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    { name: "search_genes", description: "Search the gene market by keyword or category", inputSchema: { type: "object", properties: { keyword: { type: "string" }, category: { type: "string" } } } },
    { name: "get_gene_detail", description: "Get detailed information about a specific gene", inputSchema: { type: "object", properties: { gene_id: { type: "string" } }, required: ["gene_id"] } },
    { name: "request_gene_learning", description: "Submit a request to learn (install) a gene on my instance", inputSchema: { type: "object", properties: { instance_id: { type: "string" }, gene_slug: { type: "string" }, reason: { type: "string" } }, required: ["instance_id", "gene_slug"] } },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  let result: unknown;

  switch (name) {
    case "search_genes": {
      const a = args as any;
      const params = new URLSearchParams();
      if (a.keyword) params.set("keyword", a.keyword);
      if (a.category) params.set("category", a.category);
      result = await apiFetch(`/genes?${params.toString()}`);
      break;
    }
    case "get_gene_detail":
      result = await apiFetch(`/genes/${(args as any).gene_id}`);
      break;
    case "request_gene_learning": {
      const a = args as any;
      result = await apiFetch(`/instances/${a.instance_id}/genes/install`, "POST", {
        gene_slug: a.gene_slug,
      });
      break;
    }
    default:
      return { content: [{ type: "text", text: `Unknown tool: ${name}` }] };
  }
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

const transport = new StdioServerTransport();
server.connect(transport);
