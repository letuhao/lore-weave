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

export async function handleListTools(
  federation: FederationService,
  headers?: Headers,
): Promise<{
  tools: any[];
  _meta: { unavailable_providers: string[]; partial: boolean };
}> {
  // MCP fan-out (H10) — carry the per-provider availability on the list-tools
  // `_meta` so the consumer's find_tools can distinguish "no such tool" from
  // "owning provider temporarily unavailable" (→ "try again", never "I can't").
  const unavailable = federation
    .providerAvailability()
    .filter((p) => !p.available)
    .map((p) => p.name);
  // REG-P2-03 — merge the caller's per-user MCP-server tools (u_/b_ prefixed) over
  // the static System catalog. No-op (empty) when the overlay flag is off, no
  // X-User-Id envelope, or the caller has zero registrations (fast path).
  const overlay = await federation.overlayTools(extractEnvelope(headers));
  // Prepend the consumer-local `find_tools` meta-tool so a minimal surface (the public edge) can
  // advertise it + relay its calls back here. chat-service already carries find_tools as core, so
  // the duplicate is deduped by name (its active set is name-keyed) + excluded from its own search.
  return {
    tools: [FIND_TOOLS_TOOL, ...(federation.catalog() as any[]), ...overlay],
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
export async function handleFindTools(
  federation: FederationService,
  args: Record<string, unknown>,
  headers?: Headers,
): Promise<any> {
  const intent = typeof args?.intent === 'string' ? args.intent : '';
  const rawLimit = typeof args?.limit === 'number' ? args.limit : FIND_TOOLS_TOOL.inputSchema.properties.limit.default;
  const limit = Math.max(1, Math.min(25, rawLimit));
  const unavailable = federation
    .providerAvailability()
    .filter((p) => !p.available)
    .map((p) => p.name);
  // REG-P2-03 — the caller's per-user overlay tools are discoverable too, so the
  // agent can find_tools its own registered servers (not just the System catalog).
  const overlay = await federation.overlayTools(extractEnvelope(headers));
  // Exclude find_tools itself so a search never re-suggests the meta-tool.
  const { payload } = findToolsResult(
    [...federation.catalog(), ...overlay],
    intent,
    limit,
    new Set([FIND_TOOLS_NAME]),
    unavailable,
  );
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
  // it; routing it to executeTool would throw "unknown tool"). Overlay tools ARE searched (headers).
  if (name === FIND_TOOLS_NAME) {
    return handleFindTools(federation, args, headers);
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
    // REG-P2-03 — a u_/b_ prefixed tool is the caller's own registered server;
    // route it to the overlay dispatch (strip prefix → call the user endpoint)
    // instead of the static provider map (which would throw "unknown tool").
    if (federation.isOverlayTool(name)) {
      return await federation.executeOverlay(name, args, env, signal);
    }
    // Forward the MCP `_meta` channel downstream (the proven TS→Go alternate to
    // headers, §20) so a provider that reads req.Params.Meta still receives it.
    return await federation.executeTool(name, args, env, meta, signal);
  } catch (e) {
    // Full detail stays server-side only; the LLM-visible text is CLASSIFIED
    // (W0 #5): retryable transport vs upstream rejection vs unknown tool — a
    // flat "provider error" gave the model nothing to act on (5x book_list
    // dead-ended in the live audit). URL-leak protection is preserved: any
    // passed-through upstream text is sanitized of URLs/hosts first.
    log.warn(`tool '${name}' execution failed: ${e}`);
    return {
      isError: true,
      content: [{ type: 'text', text: `tool '${name}' failed: ${classifyCallToolError(e)}` }],
    };
  }
}

// ── W0 #5 — LLM-facing tool-error classification ────────────────────────

/** Strips anything address-shaped from upstream error text before it reaches
 * the model: URLs, internal `<svc>-service:port` hosts, bare host:port pairs,
 * and IPv4s. The redaction keeps the rest of the upstream's (self-authored,
 * model-actionable) message intact. */
export function sanitizeUpstreamErrorText(raw: string): string {
  return raw
    .replace(/[a-z][a-z0-9+.-]*:\/\/[^\s"'()<>]+/gi, '[redacted]') // scheme://…
    .replace(/\b[\w.-]*\b(?:service|gateway|api|db|host)\b[\w.-]*:\d{2,5}\b/gi, '[redacted]')
    .replace(/\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{2,5})?\b/g, '[redacted]')
    .replace(/\b[\w-]+\.(?:local|internal|svc|cluster)[\w.]*(?::\d{2,5})?\b/gi, '[redacted]')
    // Generic host:port catch-all (after the specific rules): `localhost:8082`,
    // `postgres:5432`, … — any bare host:port pair is address-shaped and must
    // not reach the model, whatever the hostname looks like.
    .replace(/\b[\w.-]+:\d{2,5}\b/g, '[redacted]')
    .trim();
}

const TRANSPORT_ERROR_RE =
  /fetch failed|ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|EPIPE|socket hang up|network|terminated|abort|timed? ?out/i;

/**
 * Classify an executeTool failure into an LLM-actionable one-liner:
 *  - unknown tool          → say so + point at find_tools (the model mistyped);
 *  - transport/timeout/5xx → "backend temporarily unreachable — retry may succeed";
 *  - upstream JSON-RPC / HTTP-4xx rejection → pass the upstream's message
 *    through, sanitized of URLs/hosts (it is server-authored and usually says
 *    exactly what to fix);
 *  - anything else         → the old generic "provider error".
 */
export function classifyCallToolError(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e ?? '');
  const code = (e as { code?: unknown })?.code;

  // federation.executeTool throws this BEFORE any network call: no provider owns the name.
  if (/^unknown tool /.test(msg)) {
    return `unknown tool — it is not in the tool catalog; call find_tools to discover valid tool names`;
  }

  // JSON-RPC error relayed from the owning provider (the TS SDK's McpError
  // formats as "MCP error <code>: <message>"). -32001 is the SDK's request
  // timeout and -32603 is the upstream's INTERNAL error — both transient
  // conditions a retry can clear, not rejections of the request's shape;
  // other codes are upstream rejections whose text is server-authored and
  // actionable.
  const mcpErr = /^MCP error (-?\d+): ([\s\S]*)$/.exec(msg);
  if (mcpErr) {
    if (mcpErr[1] === '-32001' || mcpErr[1] === '-32603') {
      return 'backend temporarily unreachable — retry may succeed';
    }
    const text = sanitizeUpstreamErrorText(mcpErr[2]);
    return text ? `rejected by the owning service: ${text}` : 'provider error';
  }

  // HTTP 408 (request timeout) / 429 (rate-limited) are transient whatever the
  // body says — classifying them as rejections told the model "don't retry" for
  // conditions that resolve by themselves.
  if (code === 408 || code === 429) {
    return 'backend temporarily unreachable or rate-limited — retry may succeed';
  }

  // Streamable-HTTP transport error carrying the upstream HTTP status: 4xx is a
  // rejection (pass sanitized text through), 5xx/undefined is retryable.
  if (typeof code === 'number' && code >= 400 && code < 500 && msg.startsWith('Streamable HTTP error:')) {
    const text = sanitizeUpstreamErrorText(msg.replace(/^Streamable HTTP error:\s*/, ''));
    return text ? `rejected by the owning service: ${text}` : 'provider error';
  }

  // Transport-level failures (connect refused, DNS, reset, abort, timeout, 5xx).
  if (TRANSPORT_ERROR_RE.test(msg) || (e as { name?: string })?.name === 'AbortError' ||
      (typeof code === 'number' && code >= 500)) {
    return 'backend temporarily unreachable — retry may succeed';
  }

  return 'provider error';
}
