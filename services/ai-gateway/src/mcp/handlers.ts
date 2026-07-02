import { Logger } from '@nestjs/common';
import type { Envelope, FederationService } from '../federation/federation.service.js';
import { FIND_TOOLS_NAME, FIND_TOOLS_TOOL, findToolsResult } from '../federation/find-tools.js';

const log = new Logger('McpProxy');

type Headers = Record<string, string | string[] | undefined> | undefined;

export function headerValue(headers: Headers, key: string): string | undefined {
  if (!headers) return undefined;
  const v = headers[key.toLowerCase()];
  return Array.isArray(v) ? v[0] : v;
}

/** Per-call identity, lifted off the request headers (SEC-1: never from the LLM). */
export function extractEnvelope(headers: Headers): Envelope {
  return {
    userId: headerValue(headers, 'x-user-id'),
    sessionId: headerValue(headers, 'x-session-id'),
    traceId: headerValue(headers, 'x-trace-id'),
    projectId: headerValue(headers, 'x-project-id'),
    mcpKeyId: headerValue(headers, 'x-mcp-key-id'),
    spendCapUsd: headerValue(headers, 'x-mcp-spend-cap-usd'),
  };
}

export function handleListTools(federation: FederationService): {
  tools: any[];
  _meta: { unavailable_providers: string[]; partial: boolean };
} {
  // MCP fan-out (H10) — carry the per-provider availability on the list-tools
  // `_meta` so the consumer's find_tools can distinguish "no such tool" from
  // "owning provider temporarily unavailable" (→ "try again", never "I can't").
  const unavailable = federation
    .providerAvailability()
    .filter((p) => !p.available)
    .map((p) => p.name);
  // Prepend the consumer-local `find_tools` meta-tool so a minimal surface (the public edge) can
  // advertise it + relay its calls back here. chat-service already carries find_tools as core, so
  // the duplicate is deduped by name (its active set is name-keyed) + excluded from its own search.
  return {
    tools: [FIND_TOOLS_TOOL, ...(federation.catalog() as any[])],
    _meta: { unavailable_providers: unavailable, partial: federation.isPartial() },
  };
}

// ── Wave C5 — resources + prompts (aggregated like tools) ──────────────

/** Shared `_meta` block: per-provider availability (H10), so a consumer can
 * tell "no such resource/prompt" from "owning provider temporarily down". */
function availabilityMeta(federation: FederationService): {
  unavailable_providers: string[];
  partial: boolean;
} {
  const unavailable = federation
    .providerAvailability()
    .filter((p) => !p.available)
    .map((p) => p.name);
  return { unavailable_providers: unavailable, partial: federation.isPartial() };
}

export function handleListResources(federation: FederationService): {
  resources: any[];
  _meta: { unavailable_providers: string[]; partial: boolean };
} {
  return { resources: federation.resourceCatalog(), _meta: availabilityMeta(federation) };
}

/** Templates ride their own list per the MCP spec (resources/templates/list) —
 * the knowledge resources are `{project_id}` templates, so WITHOUT this list
 * they would be invisible to clients (they never appear in resources/list). */
export function handleListResourceTemplates(federation: FederationService): {
  resourceTemplates: any[];
  _meta: { unavailable_providers: string[]; partial: boolean };
} {
  return {
    resourceTemplates: federation.resourceTemplateCatalog(),
    _meta: availabilityMeta(federation),
  };
}

export function handleListPrompts(federation: FederationService): {
  prompts: any[];
  _meta: { unavailable_providers: string[]; partial: boolean };
} {
  return { prompts: federation.promptCatalog(), _meta: availabilityMeta(federation) };
}

/**
 * Route a resources/read to the owning provider with the per-call envelope
 * (identity from headers, never the LLM — SEC-1; the provider enforces
 * tenancy on the read). Unlike CallTool there is no `isError` result shape
 * for reads, so a provider failure THROWS — the SDK surfaces it as a clean
 * JSON-RPC error — but with a GENERIC message: the raw `String(e)` of a
 * transport failure embeds the internal provider URL, which must never leak.
 */
export async function handleReadResource(
  federation: FederationService,
  uri: string,
  headers: Headers,
  signal?: AbortSignal,
): Promise<any> {
  const env = extractEnvelope(headers);
  if (!env.userId) {
    log.warn(`resource '${uri}' read with no X-User-Id envelope`);
  }
  try {
    return await federation.readResource(uri, env, signal);
  } catch (e) {
    log.warn(`resource '${uri}' read failed: ${e}`);
    throw new Error(`resource '${uri}' read failed: provider error`);
  }
}

/** Route a prompts/get to the owning provider — same envelope + generic-error
 * contract as {@link handleReadResource}. */
export async function handleGetPrompt(
  federation: FederationService,
  name: string,
  args: Record<string, unknown>,
  headers: Headers,
  signal?: AbortSignal,
): Promise<any> {
  const env = extractEnvelope(headers);
  try {
    return await federation.getPrompt(name, args, env, signal);
  } catch (e) {
    log.warn(`prompt '${name}' get failed: ${e}`);
    throw new Error(`prompt '${name}' get failed: provider error`);
  }
}

/**
 * Handle a local `find_tools` call (the lazy-discovery meta-tool). It is consumer-local (OD-1):
 * it searches ONLY the federation catalogue, never a provider — so it needs no envelope/ownership
 * (none of the caller's data is touched). Returns a standard MCP CallToolResult; the matched names
 * are carried in `structuredContent.tools` for the agent to call next.
 */
export function handleFindTools(federation: FederationService, args: Record<string, unknown>): any {
  const intent = typeof args?.intent === 'string' ? args.intent : '';
  const rawLimit = typeof args?.limit === 'number' ? args.limit : FIND_TOOLS_TOOL.inputSchema.properties.limit.default;
  const limit = Math.max(1, Math.min(25, rawLimit));
  const unavailable = federation
    .providerAvailability()
    .filter((p) => !p.available)
    .map((p) => p.name);
  // Exclude find_tools itself so a search never re-suggests the meta-tool.
  const { payload } = findToolsResult(federation.catalog(), intent, limit, new Set([FIND_TOOLS_NAME]), unavailable);
  return {
    content: [{ type: 'text', text: JSON.stringify(payload) }],
    structuredContent: payload,
  };
}

/**
 * Route a CallTool to the owning provider with the per-call envelope. A provider
 * failure becomes an MCP tool error (`isError`), NOT a transport 5xx — so the
 * consumer's tool-loop reports "tool failed" to the LLM and carries on (the
 * house degradation contract).
 */
export async function handleCallTool(
  federation: FederationService,
  name: string,
  args: Record<string, unknown>,
  headers: Headers,
  meta?: unknown,
  // D-PLANNER-INFLIGHT-ABORT (#19) — aborts when the inbound MCP request's
  // transport closes (chat-turn stop). Threaded to the downstream tool call so a
  // heavy in-flight tool (the ~39s glossary_plan) is cancelled, not orphaned.
  signal?: AbortSignal,
): Promise<any> {
  // find_tools is consumer-local — handle it HERE without a downstream provider (no provider owns
  // it; routing it to executeTool would throw "unknown tool"). No envelope needed (OD-1).
  if (name === FIND_TOOLS_NAME) {
    return handleFindTools(federation, args);
  }

  const env = extractEnvelope(headers);
  // A CallTool with no caller identity is almost always a bug. Per-tool identity
  // enforcement stays on the PROVIDER (SEC-2 — and some tools, e.g.
  // glossary_list_system_standards, are legitimately global), so the gateway forwards
  // regardless but logs the anomaly for observability rather than failing blind.
  if (!env.userId) {
    log.warn(`tool '${name}' called with no X-User-Id envelope`);
  }
  try {
    // Forward the MCP `_meta` channel downstream (the proven TS→Go alternate to
    // headers, §20) so a provider that reads req.Params.Meta still receives it.
    return await federation.executeTool(name, args, env, meta, signal);
  } catch (e) {
    // Full detail stays server-side only. The LLM-visible text is GENERIC: a
    // transport failure's `String(e)` includes the internal provider URL (e.g.
    // http://book-service:8082/mcp), which must never leak to the model.
    log.warn(`tool '${name}' execution failed: ${e}`);
    return {
      isError: true,
      content: [{ type: 'text', text: `tool '${name}' failed: provider error` }],
    };
  }
}
