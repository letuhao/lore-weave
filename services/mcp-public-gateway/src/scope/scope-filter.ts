import type { Logger } from '@nestjs/common';
import { FIND_TOOLS_NAME, TOOL_LIST_NAME, TOOL_LOAD_NAME, TOOL_POLICY, WILDCARD_SCOPE, filterTools, isToolAllowed, knownTool } from './tool-policy.js';

/** The always-present discovery meta-tools — never scope-collapsed off tools/list, never drift-warned. */
const DISCOVERY_META_TOOLS: ReadonlySet<string> = new Set([FIND_TOOLS_NAME, TOOL_LIST_NAME, TOOL_LOAD_NAME]);

/**
 * Edge scope enforcement (PUB-3 / H-E / H-F), the SECOND of the two checks (the
 * provider's ownership/tier gate is the first). Two halves:
 *
 *   - REQUEST gate (`gateRequestBody`): a `tools/call` to a tool outside the key's
 *     tier∩domain scope is denied HERE, before the relay — default-deny / fail-closed.
 *   - RESPONSE filter (`filterListResponseText`): a `tools/list` response is rewritten
 *     to advertise only the tools the key may call (so an external agent never even
 *     sees out-of-scope tools).
 *
 * A `*` (wildcard) scope — the dev/smoke static key — bypasses both.
 */

const JSONRPC_METHOD_NOT_ALLOWED = -32601;

interface JsonRpcRequest {
  jsonrpc?: unknown;
  method?: unknown;
  params?: { name?: unknown } | undefined;
  id?: unknown;
}

function isToolCall(msg: JsonRpcRequest): msg is JsonRpcRequest & { params: { name: string } } {
  return msg?.method === 'tools/call' && typeof msg?.params?.name === 'string';
}

function denyError(id: unknown, toolName: string): unknown {
  return {
    jsonrpc: '2.0',
    error: {
      code: JSONRPC_METHOD_NOT_ALLOWED,
      // Anti-oracle: an unknown tool and an out-of-scope tool give the SAME message,
      // so a probing agent can't distinguish "doesn't exist" from "not in my scope".
      message: `tool '${toolName}' is not available to this key`,
    },
    id: id ?? null,
  };
}

/**
 * Inspect the inbound JSON-RPC body. If it contains any `tools/call` to a tool the
 * key may not call, return a JSON-RPC error response to send INSTEAD of relaying
 * (default-deny). Returns `null` when the whole body is permitted to relay.
 *
 * Handles a single message or a JSON-RPC batch (array). For a batch, if ANY call is
 * denied the WHOLE batch is rejected (fail-closed) with per-id errors — we never
 * partially relay, which would be hard to reconcile and could leak.
 */
export function gateRequestBody(body: unknown, scopes: readonly string[]): unknown | null {
  if (scopes.includes(WILDCARD_SCOPE)) return null;

  const messages: JsonRpcRequest[] = Array.isArray(body)
    ? (body as JsonRpcRequest[])
    : body && typeof body === 'object'
      ? [body as JsonRpcRequest]
      : [];

  const calls = messages.filter(isToolCall);
  if (calls.length === 0) return null; // no tool calls → nothing to gate here

  const denied = calls.filter((m) => !isToolAllowed(m.params.name, scopes));
  if (denied.length === 0) return null;

  // At least one denied call → reject the whole request, fail-closed.
  const errors = denied.map((m) => denyError(m.id, m.params.name));
  return Array.isArray(body) ? errors : errors[0];
}

/**
 * Classify the request as a WRITE for the rate-limiter's fail policy (PUB-8): a
 * `tools/call` to a tool whose tier is `write_auto`/`write_confirm`. Everything
 * else — reads, `tools/list`, `initialize`, `ping`, and any unknown/unclassified
 * tool — is treated as a READ (an unknown tool is denied by the scope gate anyway,
 * and reads fail OPEN, the safe-for-availability default). A batch is a write if
 * ANY call in it is a write.
 */
export function isWriteRequest(body: unknown): boolean {
  const messages: JsonRpcRequest[] = Array.isArray(body)
    ? (body as JsonRpcRequest[])
    : body && typeof body === 'object'
      ? [body as JsonRpcRequest]
      : [];
  return messages.some((m) => {
    if (!isToolCall(m)) return false;
    // confirm_action is a synthetic edge tool (absent from TOOL_POLICY) that EXECUTES a
    // proposed Tier-W action — treat it as a write so it fails CLOSED on a store outage.
    if (m.params.name === 'confirm_action') return true;
    const tier = TOOL_POLICY[m.params.name]?.tier;
    return tier === 'write_auto' || tier === 'write_confirm';
  });
}

/**
 * The tool name iff the body is a SINGLE (non-batch) `tools/call` to a `write_confirm`
 * tool — the only shape the P4 approval-divert handles. Returns null for a batch, a
 * non-call, or a call to any other tier (write_auto/read/paid_read are never diverted).
 * A batch containing a write_confirm propose is intentionally NOT diverted in v1.
 */
export function singleWriteConfirmToolName(body: unknown): string | null {
  if (Array.isArray(body)) return null; // batch — out of scope for the divert
  if (!body || typeof body !== 'object') return null;
  const msg = body as JsonRpcRequest;
  if (!isToolCall(msg)) return null;
  return TOOL_POLICY[msg.params.name]?.tier === 'write_confirm' ? msg.params.name : null;
}

/**
 * Count the `tools/call` entries in the request — the rate-limit weight, so a
 * JSON-RPC BATCH of N calls costs N against the per-minute limit (not 1). Returns
 * 0 for a body with no tool calls (the caller floors the weight at 1).
 */
export function countToolCalls(body: unknown): number {
  const messages: JsonRpcRequest[] = Array.isArray(body)
    ? (body as JsonRpcRequest[])
    : body && typeof body === 'object'
      ? [body as JsonRpcRequest]
      : [];
  return messages.filter(isToolCall).length;
}

/**
 * The `tools/call` tool names in the request (one per call; a batch yields N). Used
 * to build per-call audit rows (H-O). Empty when the body has no tool calls.
 */
export function toolCallNames(body: unknown): string[] {
  const messages: JsonRpcRequest[] = Array.isArray(body)
    ? (body as JsonRpcRequest[])
    : body && typeof body === 'object'
      ? [body as JsonRpcRequest]
      : [];
  return messages.filter(isToolCall).map((m) => m.params.name);
}

/** The first JSON-RPC method in the body (for auditing a non-call request); '' when absent. */
export function firstMethod(body: unknown): string {
  const messages: JsonRpcRequest[] = Array.isArray(body)
    ? (body as JsonRpcRequest[])
    : body && typeof body === 'object'
      ? [body as JsonRpcRequest]
      : [];
  const m = messages.find((x) => typeof x?.method === 'string');
  return m && typeof m.method === 'string' ? m.method : '';
}

/** True iff the inbound body is (or contains) a `tools/list` request. */
export function isListRequest(body: unknown): boolean {
  const messages: JsonRpcRequest[] = Array.isArray(body)
    ? (body as JsonRpcRequest[])
    : body && typeof body === 'object'
      ? [body as JsonRpcRequest]
      : [];
  return messages.some((m) => m?.method === 'tools/list');
}

interface ToolsListResult {
  result?: { tools?: unknown };
}

function filterOneListMessage(
  msg: ToolsListResult,
  scopes: readonly string[],
  log?: Logger,
  activated?: ReadonlySet<string>,
): void {
  const tools = msg?.result?.tools;
  if (!Array.isArray(tools)) return;
  // Drift signal: any advertised tool not in the policy table is being denied —
  // surface it so a newly-federated tool gets classified rather than silently lost.
  // find_tools is the exception (always-allowed meta-tool) — never warn on it.
  if (log) {
    for (const t of tools) {
      const n = (t as { name?: unknown })?.name;
      if (typeof n === 'string' && !DISCOVERY_META_TOOLS.has(n) && !knownTool(n)) {
        log.warn(`scope-filter: federated tool '${n}' not in policy table — denied (classify it in tool-policy.ts)`);
      }
    }
  }
  let out = filterTools(tools as Array<{ name?: unknown }>, scopes);
  // LAZY TOOL-LOADING (the per-session state machine): when an `activated` set is supplied,
  // collapse the scope-filtered list to the SESSION SURFACE — `find_tools` (always, the
  // discovery entrypoint) plus only the tools the agent has ACTIVATED this session. A fresh
  // session → just find_tools; the surface grows as find_tools activates tools. `*` (wildcard
  // dev key) is already returned whole by filterTools, so it never reaches this collapse.
  if (activated && !scopes.includes(WILDCARD_SCOPE)) {
    out = out.filter((t) => {
      const n = (t as { name?: unknown }).name;
      // The discovery meta-tools (find_tools + the deterministic pair tool_list/tool_load) are
      // ALWAYS present — they are the entrypoints; the surface grows as they activate tools.
      return (typeof n === 'string' && DISCOVERY_META_TOOLS.has(n)) || (typeof n === 'string' && activated.has(n));
    });
  }
  msg.result!.tools = out;
}

/**
 * Rewrite a `tools/list` JSON response so it advertises only in-scope tools.
 *
 * ai-gateway runs with `enableJsonResponse: true`, so list responses are a single
 * JSON document (object or batch array). If the body can't be parsed as JSON (an
 * unexpected SSE/error shape), we FAIL CLOSED: return an empty tool list rather than
 * leak the unfiltered catalogue.
 */
export function filterListResponseText(
  text: string,
  scopes: readonly string[],
  log?: Logger,
  activated?: ReadonlySet<string>,
): string {
  if (scopes.includes(WILDCARD_SCOPE)) return text;
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    log?.warn('scope-filter: tools/list response was not JSON — failing closed (empty list)');
    return JSON.stringify({ jsonrpc: '2.0', result: { tools: [] }, id: null });
  }
  if (Array.isArray(parsed)) {
    for (const m of parsed) filterOneListMessage(m as ToolsListResult, scopes, log, activated);
  } else if (parsed && typeof parsed === 'object') {
    filterOneListMessage(parsed as ToolsListResult, scopes, log, activated);
  }
  return JSON.stringify(parsed);
}

/**
 * True iff the body is a SINGLE (non-batch) `tools/call` to `find_tools` — the lazy-discovery
 * meta-tool whose RESULT the edge scope-filters + whose matches it activates into the session.
 */
export function isFindToolsCall(body: unknown): boolean {
  if (Array.isArray(body)) return false;
  if (!body || typeof body !== 'object') return false;
  const msg = body as JsonRpcRequest;
  return isToolCall(msg) && msg.params.name === FIND_TOOLS_NAME;
}

interface FindToolsMatch {
  name?: unknown;
}

/**
 * Scope-filter ONE find_tools CallToolResult IN PLACE — drop out-of-scope matches from BOTH the
 * structuredContent and the mirrored text content block (so a client reading either sees the same
 * scoped set). Returns the in-scope matched names (to SADD into the session). Shared by the single
 * and the batch path so they enforce the identical anti-oracle contract.
 */
/**
 * Entitlement-opacity fix (item #6): when this key's OWN scope-filter is what strips a
 * previously non-empty match/enumeration set down to zero, the caller otherwise gets a bare
 * `{tools:[], enumerated:true}` indistinguishable from ai-gateway's own "domain genuinely has
 * no tools" case (its `note` field — see find-tools.ts `findToolsResult`/`enumerateGroup` —
 * covers THAT case correctly and must not be duplicated here). This is a DIFFERENT condition:
 * the domain has tools, this key just isn't entitled to them. Deliberately a different field
 * name (`scope_note`, not `note`) so the two never collide if both legs somehow both fired.
 */
const ENTITLEMENT_GAP_NOTE =
  'this domain has tools, but they are not enabled for this API key — ask the key owner to grant access';

function filterOneFindToolsResult(result: unknown, scopes: readonly string[]): string[] {
  if (!result || typeof result !== 'object') return [];
  const inScope = new Set<string>();
  const sc = (result as { structuredContent?: { tools?: unknown; scope_note?: unknown } }).structuredContent;
  if (sc && Array.isArray(sc.tools)) {
    const hadMatches = sc.tools.length > 0;
    const filtered = (sc.tools as FindToolsMatch[]).filter((m) => {
      const n = typeof m?.name === 'string' ? m.name : '';
      const ok = n !== '' && isToolAllowed(n, scopes);
      if (ok) inScope.add(n);
      return ok;
    });
    sc.tools = filtered;
    // Only fire when THIS filtering step is what caused the non-empty→empty transition —
    // if ai-gateway already handed back an empty set, its own `note` already explains why.
    if (hadMatches && filtered.length === 0) {
      sc.scope_note = ENTITLEMENT_GAP_NOTE;
    }
    const content = (result as { content?: unknown }).content;
    if (Array.isArray(content) && content[0] && typeof content[0] === 'object') {
      (content[0] as { text?: unknown }).text = JSON.stringify(sc);
    }
  }
  return [...inScope];
}

/**
 * Scope-filter a SINGLE (non-batch) `find_tools` RESULT (anti-oracle) + collect the in-scope
 * matched names to activate. ai-gateway searches the FULL catalogue, so its matches can include
 * tools outside this key's scope; the edge intersects them with `isToolAllowed` so an external
 * agent never even DISCOVERS an out-of-scope tool (same anti-oracle contract as the list filter).
 * Returns the rewritten response text + the in-scope matched names (to SADD into the session). On
 * a `*` key, or any non-object / unparseable body, returns the text unchanged + no names.
 */
export function scopeFilterFindToolsResult(
  text: string,
  scopes: readonly string[],
): { text: string; activatedNames: string[] } {
  if (scopes.includes(WILDCARD_SCOPE)) return { text, activatedNames: [] };
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { text, activatedNames: [] }; // SSE / non-JSON — never fabricate
  }
  // A single tools/call response is a JSON-RPC object with `result` (an MCP CallToolResult:
  // `{ content: [...], structuredContent?: { tools: [...] } }`).
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { text, activatedNames: [] };
  const names = filterOneFindToolsResult((parsed as { result?: unknown }).result, scopes);
  return { text: JSON.stringify(parsed), activatedNames: names };
}

// ── WS-1a · tool_list / tool_load edge scope-filter + activation (contracts.md C2) ──────────────

/** True iff the body is a SINGLE `tools/call` to `tool_list`. */
export function isToolListCall(body: unknown): boolean {
  if (Array.isArray(body) || !body || typeof body !== 'object') return false;
  const msg = body as JsonRpcRequest;
  return isToolCall(msg) && msg.params.name === TOOL_LIST_NAME;
}

/** True iff the body is a SINGLE `tools/call` to `tool_load`. */
export function isToolLoadCall(body: unknown): boolean {
  if (Array.isArray(body) || !body || typeof body !== 'object') return false;
  const msg = body as JsonRpcRequest;
  return isToolCall(msg) && msg.params.name === TOOL_LOAD_NAME;
}

/** Scope-filter a `{name}[]` tool array IN PLACE by `isToolAllowed`, optionally collecting the
 * in-scope names. Returns whether the input was non-empty (to detect a non-empty→empty collapse). */
function filterNamedToolsByScope(
  tools: unknown,
  scopes: readonly string[],
  collect?: Set<string>,
): { filtered: unknown[]; hadAny: boolean } {
  if (!Array.isArray(tools)) return { filtered: [], hadAny: false };
  const hadAny = tools.length > 0;
  const filtered = (tools as Array<{ name?: unknown }>).filter((t) => {
    const n = typeof t?.name === 'string' ? t.name : '';
    const ok = n !== '' && isToolAllowed(n, scopes);
    if (ok && collect) collect.add(n);
    return ok;
  });
  return { filtered, hadAny };
}

/** Rewrite the mirrored `content[0].text` to match the (now scope-filtered) structuredContent. */
function syncContentText(result: unknown, sc: unknown): void {
  const content = (result as { content?: unknown }).content;
  if (Array.isArray(content) && content[0] && typeof content[0] === 'object') {
    (content[0] as { text?: unknown }).text = JSON.stringify(sc);
  }
}

/**
 * Scope-filter a SINGLE `tool_load` RESULT (anti-oracle) + collect the in-scope loaded names to
 * ACTIVATE (making a subsequent raw `tools/call` permitted — the deterministic analogue of the
 * find_tools→activate path). ai-gateway loads from the FULL catalogue; the edge drops any tool
 * outside this key's scope so an external agent never even loads an out-of-scope schema.
 */
export function scopeFilterToolLoadResult(
  text: string,
  scopes: readonly string[],
): { text: string; activatedNames: string[] } {
  if (scopes.includes(WILDCARD_SCOPE)) return { text, activatedNames: [] };
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { text, activatedNames: [] };
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { text, activatedNames: [] };
  const result = (parsed as { result?: unknown }).result;
  const names = new Set<string>();
  if (result && typeof result === 'object') {
    const sc = (result as { structuredContent?: { tools?: unknown; scope_note?: unknown } }).structuredContent;
    if (sc && Array.isArray(sc.tools)) {
      const { filtered, hadAny } = filterNamedToolsByScope(sc.tools, scopes, names);
      sc.tools = filtered;
      if (hadAny && filtered.length === 0) sc.scope_note = ENTITLEMENT_GAP_NOTE;
      syncContentText(result, sc);
    }
  }
  return { text: JSON.stringify(parsed), activatedNames: [...names] };
}

/**
 * Scope-filter a SINGLE `tool_list` RESULT (anti-oracle) — drop out-of-scope tools from both the
 * flat `tools` list and the grouped `categories` map, recompute `count`, and set `scope_note` when
 * THIS key's scope is what emptied a non-empty set (entitlement opacity, feedback #6). Listing does
 * NOT activate (only tool_load does), so this returns only the rewritten text.
 */
export function scopeFilterToolListResult(text: string, scopes: readonly string[]): string {
  if (scopes.includes(WILDCARD_SCOPE)) return text;
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return text;
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return text;
  const result = (parsed as { result?: unknown }).result;
  if (result && typeof result === 'object') {
    const sc = (result as { structuredContent?: Record<string, unknown> }).structuredContent;
    if (sc && typeof sc === 'object') {
      let emptiedFromNonEmpty = false;
      if (Array.isArray(sc.tools)) {
        const { filtered, hadAny } = filterNamedToolsByScope(sc.tools, scopes);
        sc.tools = filtered;
        sc.count = filtered.length;
        if (hadAny && filtered.length === 0) emptiedFromNonEmpty = true;
      }
      const cats = sc.categories;
      if (cats && typeof cats === 'object') {
        let total = 0;
        let hadAny = false;
        for (const cat of Object.keys(cats as Record<string, unknown>)) {
          const { filtered, hadAny: h } = filterNamedToolsByScope((cats as Record<string, unknown>)[cat], scopes);
          if (h) hadAny = true;
          if (filtered.length === 0) delete (cats as Record<string, unknown>)[cat];
          else {
            (cats as Record<string, unknown>)[cat] = filtered;
            total += filtered.length;
          }
        }
        sc.count = total;
        if (hadAny && total === 0) emptiedFromNonEmpty = true;
      }
      if (emptiedFromNonEmpty) sc.scope_note = ENTITLEMENT_GAP_NOTE;
      syncContentText(result, sc);
    }
  }
  return JSON.stringify(parsed);
}

/**
 * The set of JSON-RPC `idKey`s for the `find_tools` `tools/call`s in `body` (single or batch).
 * Used to scope-filter a BATCHED find_tools result by matching the response item back to its
 * request — so a find_tools smuggled inside a batch can't bypass the single-call anti-oracle
 * filter. A find_tools call carrying no id (a notification) is impossible (tools/call always
 * carries an id), so the ` null` sentinel never wrongly matches a non-find_tools item.
 */
export function findToolsCallIdKeys(body: unknown): Set<string> {
  const messages: JsonRpcRequest[] = Array.isArray(body)
    ? (body as JsonRpcRequest[])
    : body && typeof body === 'object'
      ? [body as JsonRpcRequest]
      : [];
  const ids = new Set<string>();
  for (const m of messages) {
    if (isToolCall(m) && m.params.name === FIND_TOOLS_NAME) ids.add(idKey(m.id));
  }
  return ids;
}

/**
 * Batch parallel of `scopeFilterFindToolsResult`: scope-filter EVERY `find_tools` result in a
 * BATCHED `tools/call` RESPONSE, matched to its request by id (`findToolsIds`). Closes the
 * anti-oracle hole where a `find_tools` smuggled inside a JSON-RPC batch relayed its FULL-catalogue
 * matches unfiltered. Only items whose id is a find_tools request are touched — a mixed batch's
 * other tool results (which may legitimately carry a `name`-bearing list of their own data) are
 * left intact. Returns the rewritten text + the union of in-scope matched names.
 *
 * Handles BOTH response shapes, because the upstream (ai-gateway, enableJsonResponse) COLLAPSES a
 * single-element batch REQUEST into a single OBJECT response (not a 1-element array) — the exact
 * bypass an adversary uses (`[{find_tools}]` → object → the array-only filter would miss it). An
 * array response → filter each matching item; a single object whose id matches → filter it. On a
 * `*` key / empty id-set / unparseable body → unchanged + no names.
 */
export function scopeFilterFindToolsBatch(
  text: string,
  scopes: readonly string[],
  findToolsIds: ReadonlySet<string>,
): { text: string; activatedNames: string[] } {
  if (scopes.includes(WILDCARD_SCOPE) || findToolsIds.size === 0) return { text, activatedNames: [] };
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { text, activatedNames: [] }; // SSE / non-JSON — never fabricate
  }
  const names = new Set<string>();
  const handleItem = (item: unknown): void => {
    if (!item || typeof item !== 'object') return;
    if (!findToolsIds.has(idKey((item as { id?: unknown }).id))) return; // id-match: only find_tools results
    for (const n of filterOneFindToolsResult((item as { result?: unknown }).result, scopes)) names.add(n);
  };
  if (Array.isArray(parsed)) {
    for (const item of parsed) handleItem(item);
  } else {
    handleItem(parsed); // upstream collapsed a single-element batch into one object response
  }
  return { text: JSON.stringify(parsed), activatedNames: [...names] };
}

// ─────────────────────────────────────────────────────────────────────────────
// P4 slice F (H17) — multi-step partial-failure honesty.
//
// A JSON-RPC BATCH (`Array.isArray(body)`) that partially lands must report WHAT
// ACTUALLY LANDED per step, not an opaque all-or-nothing blob. We attach a
// `step_outcomes` array to a successfully-relayed batch so the agent can report
// honestly per step. The EDGE is the source of truth for what it did: which steps
// it would deny at the scope gate vs which it relayed; for relayed steps we refine
// to `failed` iff the upstream JSON-RPC entry for that step's id is an `error`.
//
// SINGLE (non-batch) requests are never touched — backward-compat (the wrapper is
// only invoked for `Array.isArray(body)`). A batch-level failure (rate-limit /
// upstream-down) never reaches this code — it stays a single error envelope.
// ─────────────────────────────────────────────────────────────────────────────

/** The per-step outcome an agent sees: edge-denied, relayed-ok, or relayed-but-the-step-errored. */
export type StepOutcome = 'relayed' | 'denied_scope' | 'failed';

export interface RequestStep {
  /** The JSON-RPC id of this request step (null when the element carried none — a notification). */
  id: unknown;
  /** The `tools/call` tool name, else the JSON-RPC method, else null (a malformed element). */
  name: string | null;
  /** True iff this element is a `tools/call` (only these are scope-gated / cost-bearing). */
  isToolCall: boolean;
}

export interface StepOutcomeEntry {
  id: unknown;
  name: string | null;
  outcome: StepOutcome;
}

/** True iff the body is a JSON-RPC batch (array). The ONLY shape slice F enriches. */
export function isBatchBody(body: unknown): boolean {
  return Array.isArray(body);
}

/**
 * Parse a request body into its ordered per-step descriptors. Faithful to the wire
 * order so a `step_outcomes` array lines up 1:1 with the request the agent sent.
 * Works for a single message (length-1) or a batch; the caller only enriches batches.
 */
export function parseRequestSteps(body: unknown): RequestStep[] {
  const messages: JsonRpcRequest[] = Array.isArray(body)
    ? (body as JsonRpcRequest[])
    : body && typeof body === 'object'
      ? [body as JsonRpcRequest]
      : [];
  return messages.map((m) => {
    const tc = isToolCall(m);
    const name = tc
      ? (m as JsonRpcRequest & { params: { name: string } }).params.name
      : typeof m?.method === 'string'
        ? m.method
        : null;
    return { id: m?.id ?? null, name, isToolCall: tc };
  });
}

/** Index a parsed upstream batch response by JSON-RPC id → whether that entry is an error. */
function upstreamErrorById(upstreamText: string): Map<string, boolean> | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(upstreamText);
  } catch {
    return null; // not JSON (SSE / unexpected) — can't refine; treat relayed steps as relayed
  }
  if (!Array.isArray(parsed)) return null; // not a batch response array — no per-step refinement
  const map = new Map<string, boolean>();
  for (const entry of parsed) {
    if (entry && typeof entry === 'object') {
      const id = (entry as { id?: unknown }).id;
      const hasError = (entry as { error?: unknown }).error != null;
      map.set(idKey(id), hasError);
    }
  }
  return map;
}

/**
 * Map of `idKey(id)` → tool name for every `write_confirm` `tools/call` in the body (single
 * or batch). The batch-divert (D-PMCP-BATCH-WCONFIRM-DIVERT) uses this to divert ONLY genuine
 * write_confirm request steps — the per-batch parallel of `singleWriteConfirmToolName`. A
 * response item is diverted iff its id matches a write_confirm request step AND its result
 * carries a routable propose (so a non-write tool that happens to echo a `confirm_token`-named
 * field is never diverted). A notification (no id) can't be a tools/call, so it never appears.
 */
export function writeConfirmCallsById(body: unknown): Map<string, string> {
  const messages: JsonRpcRequest[] = Array.isArray(body)
    ? (body as JsonRpcRequest[])
    : body && typeof body === 'object'
      ? [body as JsonRpcRequest]
      : [];
  const map = new Map<string, string>();
  for (const m of messages) {
    if (isToolCall(m) && TOOL_POLICY[m.params.name]?.tier === 'write_confirm') {
      map.set(idKey(m.id), m.params.name);
    }
  }
  return map;
}

/** Stable string key for matching a JSON-RPC id across request/response (number|string|null). */
export function idKey(id: unknown): string {
  if (id === null || id === undefined) return ' null';
  return `${typeof id}:${String(id)}`;
}

/**
 * Build the per-step `step_outcomes` for a BATCH relay (H17). One entry per request
 * step, in wire order:
 *   - `denied_scope` — the edge would default-deny this tool call (out-of-scope / unknown).
 *   - `failed`       — relayed, but the upstream JSON-RPC entry for this id came back an error.
 *   - `relayed`      — relayed and (as far as the edge can tell) landed.
 *
 * A `*` (wildcard) key relays everything, so no step is `denied_scope`. When the upstream
 * body is not a parseable JSON-RPC batch array (SSE / a single error), relayed steps stay
 * `relayed` — we never FABRICATE per-step success or failure we can't see.
 */
export function buildStepOutcomes(
  body: unknown,
  scopes: readonly string[],
  upstreamText: string,
): StepOutcomeEntry[] {
  const steps = parseRequestSteps(body);
  const wildcard = scopes.includes(WILDCARD_SCOPE);
  const errById = upstreamErrorById(upstreamText);
  return steps.map((s) => {
    // The edge is the source of truth for what it relayed vs denied.
    if (s.isToolCall && s.name != null && !wildcard && !isToolAllowed(s.name, scopes)) {
      return { id: s.id, name: s.name, outcome: 'denied_scope' as StepOutcome };
    }
    // Relayed: refine to `failed` only when the upstream entry for THIS id is an error.
    const errored = errById?.get(idKey(s.id)) === true;
    return { id: s.id, name: s.name, outcome: (errored ? 'failed' : 'relayed') as StepOutcome };
  });
}

/**
 * D-PMCP-AUDIT-DOWNSTREAM-OUTCOME: true iff `body` is a SINGLE `tools/call` (NOT a
 * batch) AND the upstream 2xx response is a JSON-RPC object carrying an `error` member —
 * i.e. the edge relayed successfully but the TOOL itself returned an error (a downstream
 * denial / validation / tool failure). The H-O audit uses this to record `tool_error`
 * instead of a misleading `relayed` (a JSON-RPC error rides a 200, so HTTP status alone
 * can't tell). Batches are NOT refined here — their per-step honesty rides the response's
 * `_meta.step_outcome` (slice F); a batch's coarse per-key audit row stays `relayed`
 * (documented ambiguity). Non-JSON / SSE / array bodies → false (never fabricate).
 */
export function singleToolCallErrored(body: unknown, upstreamText: string): boolean {
  if (Array.isArray(body)) return false; // batch — not refined here
  const step = parseRequestSteps(body)[0];
  if (!step || !step.isToolCall) return false; // only a tools/call bears a tool outcome
  let parsed: unknown;
  try {
    parsed = JSON.parse(upstreamText);
  } catch {
    return false; // SSE / non-JSON — can't tell, don't fabricate
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return false;
  return (parsed as { error?: unknown }).error != null;
}

/**
 * Annotate a successfully-relayed BATCH response IN PLACE with each step's edge verdict —
 * keeping the bare JSON-RPC array shape (H-M transport-transparency). Each response item
 * gains an additive top-level `_meta.step_outcome` (`relayed` | `failed` | `denied_scope`):
 * a strict JSON-RPC client ignores the unknown field, while an agent reads it for honest
 * per-step status. ADDITIVE + backward-compatible:
 *   - A SINGLE (non-array) request → upstream text returned UNCHANGED (byte-for-byte).
 *   - A batch whose upstream body is not a parseable JSON-RPC array (SSE / single error) →
 *     returned UNCHANGED (we never reshape what we can't parse, and never FABRICATE).
 *   - A batch JSON-RPC array → the SAME array, each object item carrying `_meta.step_outcome`.
 */
export function annotateBatchStepOutcomes(
  body: unknown,
  scopes: readonly string[],
  upstreamText: string,
): string {
  if (!Array.isArray(body)) return upstreamText; // single request — never touched
  let parsed: unknown;
  try {
    parsed = JSON.parse(upstreamText);
  } catch {
    return upstreamText; // not JSON (SSE) — leave as-is
  }
  if (!Array.isArray(parsed)) return upstreamText; // not a batch response array — leave as-is
  // The edge's verdict per request-step id (denied_scope from the gate; relayed/failed
  // refined from the upstream entry). Map onto the response items by JSON-RPC id.
  const verdictById = new Map<string, StepOutcome>();
  for (const e of buildStepOutcomes(body, scopes, upstreamText)) verdictById.set(idKey(e.id), e.outcome);
  for (const item of parsed) {
    if (!item || typeof item !== 'object') continue;
    const id = (item as { id?: unknown }).id;
    const outcome =
      verdictById.get(idKey(id)) ?? ((item as { error?: unknown }).error != null ? 'failed' : 'relayed');
    const obj = item as { _meta?: Record<string, unknown> };
    obj._meta = { ...(obj._meta ?? {}), step_outcome: outcome };
  }
  return JSON.stringify(parsed);
}
