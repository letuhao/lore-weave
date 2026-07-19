import { Logger } from '@nestjs/common';
import type { Envelope, FederationService } from '../federation/federation.service.js';
import {
  FIND_TOOLS_NAME,
  FIND_TOOLS_TOOL,
  findToolsAttempts,
  findToolsResult,
  TOOL_LIST_NAME,
  TOOL_LIST_TOOL,
  TOOL_LOAD_NAME,
  TOOL_LOAD_TOOL,
  toolListResult,
  toolLoadResult,
} from '../federation/find-tools.js';
import { UI_TOOLS, UI_TOOL_NAMES, handleUiTool } from './ui-tools.js';

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
  // Prepend the consumer-local discovery meta-tools so a minimal surface (the public edge) can
  // advertise them + relay their calls back here. WS-1a (contracts.md C2): `tool_list`/`tool_load` —
  // the DETERMINISTIC pair — go FIRST (the primary discovery path, OQ1); `find_tools` follows as the
  // OPTIONAL semantic convenience. All three are deduped by name on the consumer's name-keyed active
  // set + excluded from their own listing/search.
  // Phase 3 — the consumer-local ui_* directive tools (KIND A). Like the discovery
  // meta-tools they have no downstream provider (handled in handleCallTool). The
  // per-turn advertisement gate (F7c nav-intent, studio_context) stays a CONSUMER
  // concern in chat-service, which filters this catalog; ai-gateway lists them so
  // they are discoverable + validated at one seam.
  return {
    tools: [
      TOOL_LIST_TOOL, TOOL_LOAD_TOOL, FIND_TOOLS_TOOL,
      ...UI_TOOLS,
      ...(federation.catalog() as any[]),
      ...overlay,
    ],
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
  // Part A (tool-catalog-simplification spec) — optional group scoping.
  const group = typeof args?.group === 'string' ? args.group : undefined;
  const unavailable = federation
    .providerAvailability()
    .filter((p) => !p.available)
    .map((p) => p.name);
  const envelope = extractEnvelope(headers);
  // REG-P2-03 — the caller's per-user overlay tools are discoverable too, so the
  // agent can find_tools its own registered servers (not just the System catalog).
  const overlay = await federation.overlayTools(envelope);
  // Retry-cap (design item 1) — key the per-session attempt tracker off the same
  // X-Session-Id envelope every other per-call identity read comes from (SEC-1: never the LLM).
  const isRepeatAttempt = findToolsAttempts.record(envelope.sessionId, group ?? null, intent);
  // Exclude find_tools itself so a search never re-suggests the meta-tool.
  const { payload } = findToolsResult(
    [...federation.catalog(), ...overlay],
    intent,
    limit,
    new Set([FIND_TOOLS_NAME]),
    unavailable,
    group,
    isRepeatAttempt,
  );
  return {
    content: [{ type: 'text', text: JSON.stringify(payload) }],
    structuredContent: payload,
  };
}

/**
 * Handle a local `tool_list` call (WS-1a, contracts.md C2) — the DETERMINISTIC, complete category
 * enumeration that replaces mandatory `find_tools` semantic search. Consumer-local (OD-1): reads only
 * the federation catalogue (+ the caller's per-user overlay), never a provider. Returns the visible
 * set with deprecated tools LABELED (not dropped). The public edge intersects this with the key's
 * scope (`catalog ∩ non-legacy(labeled) ∩ isToolAllowed`) — this layer contributes the first two.
 */
export async function handleToolList(
  federation: FederationService,
  args: Record<string, unknown>,
  headers?: Headers,
): Promise<any> {
  const category = typeof args?.category === 'string' ? args.category : undefined;
  const includeDeprecated = typeof args?.include_deprecated === 'boolean' ? args.include_deprecated : true;
  const overlay = await federation.overlayTools(extractEnvelope(headers));
  const { payload } = toolListResult([...federation.catalog(), ...overlay], category, includeDeprecated);
  return { content: [{ type: 'text', text: JSON.stringify(payload) }], structuredContent: payload };
}

/**
 * Handle a local `tool_load` call (WS-1a, contracts.md C2) — progressive disclosure of exact input
 * schemas by name/names/category. Pure disclosure: returns schemas, executes nothing. The matched
 * names ride `structuredContent.tools[].name` so the public edge can mark them ACTIVATED (making a
 * subsequent raw `tools/call` permitted) — the deterministic analogue of the `find_tools`→activate path.
 */
export async function handleToolLoad(
  federation: FederationService,
  args: Record<string, unknown>,
  headers?: Headers,
): Promise<any> {
  const name = typeof args?.name === 'string' ? args.name : undefined;
  const names = Array.isArray(args?.names)
    ? (args.names as unknown[]).filter((n): n is string => typeof n === 'string')
    : undefined;
  const category = typeof args?.category === 'string' ? args.category : undefined;
  const overlay = await federation.overlayTools(extractEnvelope(headers));
  const { payload } = toolLoadResult([...federation.catalog(), ...overlay], { name, names, category });
  return { content: [{ type: 'text', text: JSON.stringify(payload) }], structuredContent: payload };
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
  // The discovery meta-tools are consumer-local — handled HERE without a downstream provider (no
  // provider owns them; routing to executeTool would throw "unknown tool"). Overlay tools are
  // included (headers). tool_list/tool_load are the deterministic pair (WS-1a); find_tools optional.
  if (name === TOOL_LIST_NAME) {
    return handleToolList(federation, args, headers);
  }
  if (name === TOOL_LOAD_NAME) {
    return handleToolLoad(federation, args, headers);
  }
  if (name === FIND_TOOLS_NAME) {
    return handleFindTools(federation, args, headers);
  }
  // Phase 3 — ui_* are consumer-local directive tools: validate (enum/required) and
  // return a directive the browser acts on; an out-of-enum arg is an isError result
  // (the enum/required signal), NEVER a silent no-op. No provider, no identity needed
  // (navigation is a client effect; nothing is written server-side).
  if (UI_TOOL_NAMES.has(name)) {
    return handleUiTool(name, args);
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
      return normalizeToolResult(name, await federation.executeOverlay(name, args, env, signal));
    }
    // Forward the MCP `_meta` channel downstream (the proven TS→Go alternate to
    // headers, §20) so a provider that reads req.Params.Meta still receives it.
    // C4 — every result passes through normalizeToolResult: a provider-returned
    // isError becomes the uniform {code,message} envelope + structuredContent is
    // deduped out of a redundant content dump.
    return normalizeToolResult(name, await federation.executeTool(name, args, env, meta, signal));
  } catch (e) {
    // Full detail stays server-side only; the LLM-visible text is CLASSIFIED
    // (W0 #5): retryable transport vs upstream rejection vs unknown tool — a
    // flat "provider error" gave the model nothing to act on (5x book_list
    // dead-ended in the live audit). URL-leak protection is preserved: any
    // passed-through upstream text is sanitized of URLs/hosts first.
    // C4 — the failure now also carries a stable machine `code` (structuredContent)
    // alongside the classified human text, so a consumer can branch on the reason.
    log.warn(`tool '${name}' execution failed: ${e}`);
    return toolErrorEnvelope(name, e);
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
    return `unknown tool — it is not in the tool catalog; call tool_list to see valid tool names (or find_tools to search by intent)`;
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

// ── C4 — the uniform tool-failure envelope (contract C4) ────────────────────
//
// EVERY tool failure, from any layer, is normalized to ONE shape:
//   { code: <STABLE_CODE>, message: <human, actionable>, detail?: {...} }  (+ isError:true)
// carried in `structuredContent` (the machine field) AND mirrored into
// `content[0].text` (the model reads either). The code set is CLOSED — extend it
// only via contracts.md C4. `NOT_DISCOVERED` is deliberately distinct from
// `NOT_FOUND` ("undiscovered" ≠ "nonexistent").
export const TOOL_ERROR_CODES = [
  'VALIDATION',
  'NOT_FOUND',
  'NOT_PERMITTED',
  'NOT_DISCOVERED',
  'CONFIRM_REQUIRED',
  'CONFIRM_FAILED',
  'BUSINESS_RULE',
  'RATE_LIMITED',
  'UPSTREAM_UNAVAILABLE',
] as const;
export type ToolErrorCode = (typeof TOOL_ERROR_CODES)[number];

/** Infer a stable code from an upstream service's (self-authored) rejection text.
 * Used when the provider gave a JSON-RPC/HTTP rejection with no structured code —
 * keyword-based, conservative, defaulting to BUSINESS_RULE (the request ran and was
 * refused on its merits, not a transport fault). */
function inferCodeFromText(text: string): ToolErrorCode {
  const t = text.toLowerCase();
  // Order matters — the more-specific permission/rate signals are tested before the
  // broader "not found", so "user not permitted; record not found" resolves to
  // NOT_PERMITTED (the actionable reason) rather than NOT_FOUND.
  if (/permission|forbidden|not allowed|unauthorized|not permitted|access denied/.test(t)) return 'NOT_PERMITTED';
  if (/rate.?limit|too many requests/.test(t)) return 'RATE_LIMITED';
  if (/needs? confirmation|approval required|requires confirmation|must confirm/.test(t)) return 'CONFIRM_REQUIRED';
  if (/\bnot found\b|does not exist|no such|unknown \w+ id/.test(t)) return 'NOT_FOUND';
  if (/must be|invalid|required|malformed|expected|badrequest|bad request|not a (uuid|number|valid)/.test(t))
    return 'VALIDATION';
  return 'BUSINESS_RULE';
}

/** Map an executeTool THROW into a stable code (companion to classifyCallToolError,
 * which produces the human message; both read the same branches so they never drift). */
export function classifyCallToolErrorCode(e: unknown): ToolErrorCode {
  const msg = e instanceof Error ? e.message : String(e ?? '');
  const code = (e as { code?: unknown })?.code;

  if (/^unknown tool /.test(msg)) return 'NOT_DISCOVERED';

  const mcpErr = /^MCP error (-?\d+): ([\s\S]*)$/.exec(msg);
  if (mcpErr) {
    if (mcpErr[1] === '-32001' || mcpErr[1] === '-32603') return 'UPSTREAM_UNAVAILABLE';
    return inferCodeFromText(mcpErr[2]);
  }

  if (code === 429) return 'RATE_LIMITED';
  if (code === 408) return 'UPSTREAM_UNAVAILABLE';

  if (typeof code === 'number' && code >= 400 && code < 500 && msg.startsWith('Streamable HTTP error:')) {
    if (code === 404) return 'NOT_FOUND';
    if (code === 401 || code === 403) return 'NOT_PERMITTED';
    if (code === 400 || code === 422) return 'VALIDATION';
    if (code === 409) return 'BUSINESS_RULE';
    return inferCodeFromText(msg.replace(/^Streamable HTTP error:\s*/, ''));
  }

  if (TRANSPORT_ERROR_RE.test(msg) || (e as { name?: string })?.name === 'AbortError' ||
      (typeof code === 'number' && code >= 500)) {
    return 'UPSTREAM_UNAVAILABLE';
  }

  return 'UPSTREAM_UNAVAILABLE';
}

/** Build the C4 failure envelope for a thrown executeTool error. */
export function toolErrorEnvelope(name: string, e: unknown): {
  isError: true;
  code: ToolErrorCode;
  structuredContent: { code: ToolErrorCode; message: string };
  content: Array<{ type: 'text'; text: string }>;
} {
  const message = classifyCallToolError(e);
  const errorCode = classifyCallToolErrorCode(e);
  return {
    isError: true,
    code: errorCode,
    structuredContent: { code: errorCode, message },
    // Keep the "tool 'name' failed: …" wrapper the model already sees (W0 #5).
    content: [{ type: 'text', text: `tool '${name}' failed: ${message}` }],
  };
}

const OK_PLACEHOLDER = 'ok — see structuredContent';

/** C4 output uniformity (#9B) — normalize a SUCCESSFUL provider CallToolResult:
 *  1. A provider that returned `isError:true` (ran, then refused) is re-shaped to the
 *     SAME envelope: a stable `code` (kept if the provider already used one from the
 *     closed set, else inferred) + `message`, in structuredContent.
 *  2. When a success carries `structuredContent`, collapse a `content` that merely
 *     re-serializes it (the exact-duplicate case) to a short placeholder — the JSON
 *     lives once in structuredContent; no double-token dump. Content that is NOT a
 *     duplicate (real prose, mixed parts) is left untouched. */
export function normalizeToolResult(name: string, result: unknown): unknown {
  if (!result || typeof result !== 'object') return result;
  const r = result as {
    isError?: boolean;
    content?: unknown;
    structuredContent?: unknown;
  };

  if (r.isError === true) {
    // Only a plain object structuredContent carries a {code,message}; an array (or any
    // non-object) must NOT be spread — `{...[...]}` would index-key it and destroy the
    // array shape a consumer expects. Treat a non-object sc as "no envelope fields".
    const rawSc = r.structuredContent;
    const sc =
      rawSc && typeof rawSc === 'object' && !Array.isArray(rawSc)
        ? (rawSc as { code?: unknown; message?: unknown })
        : undefined;
    const provided = typeof sc?.code === 'string' ? (sc.code as string) : '';
    const code: ToolErrorCode = (TOOL_ERROR_CODES as readonly string[]).includes(provided)
      ? (provided as ToolErrorCode)
      : inferCodeFromText(
          typeof sc?.message === 'string'
            ? (sc.message as string)
            : firstText(r.content) || provided,
        );
    const message =
      (typeof sc?.message === 'string' && sc.message) ||
      firstText(r.content) ||
      `tool '${name}' reported an error`;
    return {
      ...r,
      isError: true,
      code,
      structuredContent: { ...(sc ?? {}), code, message },
      content: [{ type: 'text', text: message }],
    };
  }

  // Success dedup: content that exactly re-serializes structuredContent → placeholder.
  if (r.structuredContent !== undefined && Array.isArray(r.content) && r.content.length === 1) {
    const only = r.content[0] as { type?: string; text?: string };
    if (only?.type === 'text' && typeof only.text === 'string') {
      const dup = safeJsonEqual(only.text, r.structuredContent);
      if (dup) {
        return { ...r, content: [{ type: 'text', text: OK_PLACEHOLDER }] };
      }
    }
  }
  return result;
}

function firstText(content: unknown): string {
  if (Array.isArray(content) && content.length > 0) {
    const c0 = content[0] as { type?: string; text?: unknown };
    if (c0?.type === 'text' && typeof c0.text === 'string') return c0.text;
  }
  return '';
}

/** True when `text` is the JSON serialization of `obj`. Key-order SENSITIVE
 * (JSON.stringify preserves order) — this is intentional: a key-order difference just
 * means "not a byte-for-byte duplicate", so the dedup declines and leaves content intact
 * (a false negative is safe; it never wrongly collapses non-duplicate content). */
function safeJsonEqual(text: string, obj: unknown): boolean {
  try {
    return JSON.stringify(JSON.parse(text)) === JSON.stringify(obj);
  } catch {
    return false;
  }
}
