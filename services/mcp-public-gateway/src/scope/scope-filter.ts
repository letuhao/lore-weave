import type { Logger } from '@nestjs/common';
import { TOOL_POLICY, WILDCARD_SCOPE, filterTools, isToolAllowed, knownTool } from './tool-policy.js';

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

function filterOneListMessage(msg: ToolsListResult, scopes: readonly string[], log?: Logger): void {
  const tools = msg?.result?.tools;
  if (!Array.isArray(tools)) return;
  // Drift signal: any advertised tool not in the policy table is being denied —
  // surface it so a newly-federated tool gets classified rather than silently lost.
  if (log) {
    for (const t of tools) {
      const n = (t as { name?: unknown })?.name;
      if (typeof n === 'string' && !knownTool(n)) {
        log.warn(`scope-filter: federated tool '${n}' not in policy table — denied (classify it in tool-policy.ts)`);
      }
    }
  }
  msg.result!.tools = filterTools(tools as Array<{ name?: unknown }>, scopes);
}

/**
 * Rewrite a `tools/list` JSON response so it advertises only in-scope tools.
 *
 * ai-gateway runs with `enableJsonResponse: true`, so list responses are a single
 * JSON document (object or batch array). If the body can't be parsed as JSON (an
 * unexpected SSE/error shape), we FAIL CLOSED: return an empty tool list rather than
 * leak the unfiltered catalogue.
 */
export function filterListResponseText(text: string, scopes: readonly string[], log?: Logger): string {
  if (scopes.includes(WILDCARD_SCOPE)) return text;
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    log?.warn('scope-filter: tools/list response was not JSON — failing closed (empty list)');
    return JSON.stringify({ jsonrpc: '2.0', result: { tools: [] }, id: null });
  }
  if (Array.isArray(parsed)) {
    for (const m of parsed) filterOneListMessage(m as ToolsListResult, scopes, log);
  } else if (parsed && typeof parsed === 'object') {
    filterOneListMessage(parsed as ToolsListResult, scopes, log);
  }
  return JSON.stringify(parsed);
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

/** Stable string key for matching a JSON-RPC id across request/response (number|string|null). */
function idKey(id: unknown): string {
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
