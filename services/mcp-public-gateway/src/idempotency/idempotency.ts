import { TOOL_POLICY } from '../scope/tool-policy.js';

/**
 * Pure helpers for H-G edge idempotency (no I/O). The controller composes these
 * with the `Idempotency` service (the Redis side).
 *
 * The `idempotency_key` is an EDGE-only argument: agents supply it on a Tier-A
 * (`write_auto`) create to make a headless retry safe, and the edge STRIPS it
 * before relay so the underlying tool (which uses `ForbidExtra`) never sees it.
 */

const JSONRPC_IDEM_IN_PROGRESS = -32030;
/** A defensive bound on the agent-supplied key so a Redis key can't grow unbounded. */
export const MAX_IDEM_KEY_LEN = 200;

interface JsonRpcToolCall {
  method?: unknown;
  params?: { name?: unknown; arguments?: unknown } | undefined;
  id?: unknown;
}

export interface IdemInfo {
  toolName: string;
  /** The cleaned key to dedup on, or null when `idempotency_key` is present but
   *  unusable (empty / non-string / too long) — the caller still STRIPS it but
   *  does not dedup. */
  idemKey: string | null;
}

/**
 * Inspect a body for an idempotency-bearing write call. Returns non-null ONLY for a
 * SINGLE (non-batch) `tools/call` to a `write_auto` tool that carries an
 * `idempotency_key` argument — the exact shape v1 dedups. `write_confirm`
 * (propose/divert path), reads, batches, and calls without the key → null (the
 * controller then relays untouched).
 */
export function idempotentWriteCallInfo(body: unknown): IdemInfo | null {
  if (Array.isArray(body) || !body || typeof body !== 'object') return null;
  const msg = body as JsonRpcToolCall;
  if (msg.method !== 'tools/call' || typeof msg.params?.name !== 'string') return null;
  if (TOOL_POLICY[msg.params.name]?.tier !== 'write_auto') return null;
  const args = msg.params.arguments;
  if (!args || typeof args !== 'object' || !('idempotency_key' in (args as object))) return null;
  const raw = (args as Record<string, unknown>).idempotency_key;
  let idemKey: string | null = null;
  if (typeof raw === 'string') {
    const t = raw.trim();
    if (t.length > 0 && t.length <= MAX_IDEM_KEY_LEN) idemKey = t;
  }
  return { toolName: msg.params.name, idemKey };
}

/**
 * Return a shallow clone of a single `tools/call` body with
 * `params.arguments.idempotency_key` removed (the edge owns that field). Leaves a
 * body without the field — or a non-single-call body — unchanged.
 */
export function stripIdempotencyKey(body: unknown): unknown {
  if (Array.isArray(body) || !body || typeof body !== 'object') return body;
  const msg = body as JsonRpcToolCall;
  const args = msg.params?.arguments;
  if (!args || typeof args !== 'object' || !('idempotency_key' in (args as object))) return body;
  const { idempotency_key: _drop, ...rest } = args as Record<string, unknown>;
  return { ...msg, params: { ...msg.params, arguments: rest } };
}

/** The Redis dedup key: scoped per credential + tool + agent-supplied key. */
export function idempotencyRedisKey(keyId: string, toolName: string, idemKey: string): string {
  return `mcp:idem:${keyId}:${toolName}:${idemKey}`;
}

/** A JSON-RPC error telling the agent its identical request is still being processed. */
export function idempotencyInProgressError(body: unknown): unknown {
  return {
    jsonrpc: '2.0',
    error: {
      code: JSONRPC_IDEM_IN_PROGRESS,
      message: 'a request with this idempotency_key is already in progress; retry shortly',
    },
    id: jsonRpcId(body),
  };
}

/**
 * Advertise the optional `idempotency_key` argument on every `write_auto` tool in a
 * (already scope-filtered) `tools/list` response, so an agent can DISCOVER it. The
 * edge strips the key before relay, so this is an edge-surface-only schema addition
 * — a first-party caller sees the domain's original schema. Fail-safe: returns the
 * text unchanged if it isn't parseable JSON or carries no tools.
 */
export function advertiseIdempotencyKeyInList(text: string): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return text;
  }
  let touched = false;
  const visit = (msg: unknown): void => {
    const tools = (msg as { result?: { tools?: unknown } })?.result?.tools;
    if (!Array.isArray(tools)) return;
    for (const t of tools) {
      const name = (t as { name?: unknown })?.name;
      if (typeof name !== 'string' || TOOL_POLICY[name]?.tier !== 'write_auto') continue;
      const tool = t as { inputSchema?: { properties?: Record<string, unknown> } };
      if (!tool.inputSchema || typeof tool.inputSchema !== 'object') continue;
      const props = (tool.inputSchema.properties ??= {});
      if (typeof props !== 'object' || 'idempotency_key' in props) continue;
      props.idempotency_key = {
        type: 'string',
        description:
          'Optional client-generated key (≤200 chars). Reuse the SAME value when retrying this create so the gateway returns the original result instead of creating a duplicate.',
      };
      touched = true;
    }
  };
  if (Array.isArray(parsed)) parsed.forEach(visit);
  else visit(parsed);
  return touched ? JSON.stringify(parsed) : text;
}

/** Best-effort JSON-RPC id for an error envelope (null for a batch / no id). */
function jsonRpcId(body: unknown): unknown {
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    return (body as { id?: unknown }).id ?? null;
  }
  return null;
}
