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
