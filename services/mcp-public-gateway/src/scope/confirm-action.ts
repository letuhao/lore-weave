/**
 * P4 slice B — `confirm_action`, the headless self-confirm tool (PURE helpers, unit-tested).
 *
 * `confirm_action` is NOT a federated domain tool (it is a chat-service FRONTEND tool with
 * no server executor). For a key with BOTH `write_confirm` and `allow_self_confirm`, the edge
 * SYNTHESIZES it: it advertises the tool in `tools/list`, and on a call it forwards
 * {confirm_token, domain} to auth-service's self-confirm replay (tagged with the key for
 * attribution). The agent is its own second actor — bounded by scope + spend cap + audit.
 */

import { buildErrorEnvelope } from './mcp-error-envelope.js';
import { jsonRpcIdOf } from './propose-detect.js';

const JSONRPC_METHOD_NOT_ALLOWED = -32601;

export interface ConfirmActionArgs {
  confirmToken: string;
  domain: string;
}

/**
 * Detect a SINGLE `confirm_action` tools/call and extract its args, or null otherwise
 * (batch / other tool / missing args). The agent passes the `confirm_token` + `domain` it
 * received from the propose result.
 */
export function detectConfirmActionCall(body: unknown): ConfirmActionArgs | null {
  if (Array.isArray(body) || !body || typeof body !== 'object') return null;
  const m = body as { method?: unknown; params?: { name?: unknown; arguments?: unknown } };
  if (m.method !== 'tools/call' || m.params?.name !== 'confirm_action') return null;
  const args = (m.params.arguments ?? {}) as Record<string, unknown>;
  const token = args.confirm_token;
  const domain = args.domain;
  if (typeof token !== 'string' || !token) return null;
  if (typeof domain !== 'string' || !domain) return null;
  return { confirmToken: token, domain };
}

/** The synthetic `confirm_action` tool definition injected into a dual-flag key's tools/list. */
export const CONFIRM_ACTION_TOOL = {
  name: 'confirm_action',
  description:
    'Execute a previously PROPOSED high-impact (Tier-W) action that returned a confirm_token. ' +
    'Pass the confirm_token and its domain (both from the propose result). Available only to ' +
    'keys with self-confirm enabled; otherwise such actions wait for the owner to approve them.',
  inputSchema: {
    type: 'object',
    properties: {
      confirm_token: { type: 'string', description: 'The confirm_token returned by the propose tool.' },
      domain: { type: 'string', description: 'The action domain from the propose result (e.g. composition, book).' },
    },
    required: ['confirm_token', 'domain'],
  },
};

/**
 * Inject `confirm_action` into a `tools/list` response JSON (for a dual-flag key). Mirrors
 * `filterListResponseText`'s parse-or-passthrough: on unparseable JSON, returns the text
 * unchanged (the catalogue is unaffected). Idempotent — never adds a duplicate.
 */
export function injectConfirmActionTool(text: string): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return text;
  }
  const inject = (msg: unknown): void => {
    const tools = (msg as { result?: { tools?: unknown } })?.result?.tools;
    if (Array.isArray(tools) && !tools.some((t) => (t as { name?: unknown })?.name === 'confirm_action')) {
      tools.push(CONFIRM_ACTION_TOOL);
    }
  };
  if (Array.isArray(parsed)) parsed.forEach(inject);
  else inject(parsed);
  return JSON.stringify(parsed);
}

/** Anti-oracle deny for a `confirm_action` call by a key lacking the dual flag — the SAME
 * shape/message a scope-denied or unknown tool gets, so the flag's existence isn't leaked. */
export function denyConfirmAction(body: unknown): unknown {
  return {
    jsonrpc: '2.0',
    error: { code: JSONRPC_METHOD_NOT_ALLOWED, message: "tool 'confirm_action' is not available to this key" },
    id: jsonRpcIdOf(body),
  };
}

/**
 * Shape the MCP tool result the agent receives from auth's self-confirm response. A 2xx
 * executes (success result); a 409 reprice or any other non-2xx becomes an `isError` result
 * carrying the structured detail so the agent can read what happened (and re-propose).
 *
 * item #10 unification: auth-service's genuine business errors (expired / execute-failed /
 * domain-unroutable / validation — see auth-service `internal/api/util.go` `writeErr` +
 * `mcp_approvals.go`'s `internalSelfConfirm`/`writeConfirmReplayResult`) already come back as
 * `{code, message}`. When that shape is present we route it through the SAME
 * `buildErrorEnvelope` helper `invoke-tool.ts` uses, reusing auth's own code/message verbatim
 * (never inventing one). The 409 `reprice_required` outcome is a genuine DOMAIN RESULT, not an
 * error code (`{status:'reprice_required', detail}`, no `code` field) — it keeps the original
 * raw pass-through below rather than being force-fit into a code it never sent.
 */
export function confirmActionResult(body: unknown, authStatus: number, authBody: string): unknown {
  let detail: unknown = {};
  try {
    detail = JSON.parse(authBody);
  } catch {
    /* keep {} */
  }
  const ok = authStatus >= 200 && authStatus < 300;
  if (!ok) {
    const d = detail as { code?: unknown; message?: unknown };
    if (typeof d.code === 'string' && typeof d.message === 'string') {
      return buildErrorEnvelope(jsonRpcIdOf(body), d.code, d.message);
    }
  }
  return {
    jsonrpc: '2.0',
    id: jsonRpcIdOf(body),
    result: {
      content: [{ type: 'text', text: authBody || '{}' }],
      structuredContent: detail,
      ...(ok ? {} : { isError: true }),
    },
  };
}
