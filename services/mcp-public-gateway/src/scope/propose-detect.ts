/**
 * P4 / OD-2 propose detection + divert response shaping (PURE — unit-tested).
 *
 * A DEFAULT public key (allow_self_confirm=false) that calls a Tier-W tool gets a
 * propose result carrying a `confirm_token` (the action is NOT executed yet). The edge
 * must NOT hand that token to the agent — it diverts the action to the owner's approval
 * queue and returns only a `pending_human_approval` envelope. These helpers (a) detect a
 * propose result in a relayed `tools/call` response and (b) build the token-stripped
 * response the agent receives instead.
 */

/** A propose result extracted from a relayed tools/call response. */
export interface ProposeResult {
  confirmToken: string;
  domain: string;
  /** The structured propose result MINUS the token — shown to the human, never echoes the token. */
  preview: Record<string, unknown>;
  costEstimateUsd: number | null;
}

/**
 * Derive the confirm domain from a dotted/prefixed descriptor when the propose result
 * carries no explicit `domain` (mirrors the FE's `descriptorDomain`). `book.publish` →
 * `book`; a `kg_`-prefixed descriptor → `kg`. Returns null when undeterminable.
 */
export function descriptorDomain(descriptor: unknown): string | null {
  if (typeof descriptor !== 'string' || descriptor.length === 0) return null;
  if (descriptor.startsWith('kg_')) return 'kg';
  const dot = descriptor.indexOf('.');
  if (dot <= 0) return null;
  return descriptor.slice(0, dot);
}

/** Best-effort cost extraction from a propose result; null when absent/non-numeric. */
function extractCost(obj: Record<string, unknown>): number | null {
  const direct = obj.cost_estimate_usd ?? obj.cost_usd;
  if (typeof direct === 'number' && Number.isFinite(direct)) return direct;
  const est = obj.estimate;
  if (est && typeof est === 'object') {
    const c = (est as Record<string, unknown>).cost_usd;
    if (typeof c === 'number' && Number.isFinite(c)) return c;
  }
  return null;
}

/**
 * Inspect a relayed `tools/call` RESPONSE and extract a propose result, or null when it
 * is not a propose (no `confirm_token`). Single-message responses only — a batch is never
 * diverted in v1 (returns null). Robust to FastMCP's wrapping: checks `result`,
 * `result.structuredContent`, and JSON-parsed `result.content[].text`.
 */
export function detectProposeResult(responseText: string): ProposeResult | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(responseText);
  } catch {
    return null;
  }
  if (Array.isArray(parsed) || !parsed || typeof parsed !== 'object') return null;
  const result = (parsed as { result?: unknown }).result;
  if (!result || typeof result !== 'object') return null;

  const r = result as Record<string, unknown>;
  const candidates: Record<string, unknown>[] = [];
  if (r.structuredContent && typeof r.structuredContent === 'object') {
    candidates.push(r.structuredContent as Record<string, unknown>);
  }
  candidates.push(r);
  if (Array.isArray(r.content)) {
    for (const block of r.content) {
      const text = (block as { text?: unknown })?.text;
      if (typeof text === 'string') {
        try {
          const j = JSON.parse(text);
          if (j && typeof j === 'object' && !Array.isArray(j)) candidates.push(j as Record<string, unknown>);
        } catch {
          /* a non-JSON text block — ignore */
        }
      }
    }
  }

  for (const obj of candidates) {
    const token = obj.confirm_token;
    if (typeof token !== 'string' || token.length === 0) continue;
    const domain = typeof obj.domain === 'string' && obj.domain ? obj.domain : descriptorDomain(obj.descriptor);
    if (!domain) continue; // cannot route the execute without a domain
    const preview: Record<string, unknown> = { ...obj };
    delete preview.confirm_token; // never store/echo the token in the human-visible preview
    return { confirmToken: token, domain, preview, costEstimateUsd: extractCost(obj) };
  }
  return null;
}

/**
 * The token-stripped response the agent receives in place of the propose result: a faithful
 * MCP tool result (content text + structuredContent) announcing the action is queued for a
 * human. The agent gets the `approval_id` to reference, never the confirm token.
 */
export function pendingApprovalResponse(body: unknown, approvalId: string): unknown {
  const payload = { status: 'pending_human_approval', approval_id: approvalId };
  return {
    jsonrpc: '2.0',
    id: jsonRpcIdOf(body),
    result: {
      content: [{ type: 'text', text: JSON.stringify(payload) }],
      structuredContent: payload,
    },
  };
}

/**
 * Fail-closed result when the propose was detected but the approval could not be queued
 * (auth-service unreachable). The token is NEVER returned — the agent is told to retry. An
 * `isError` tool result so the agent's loop treats it as a failed step, not a success.
 */
export function proposeDivertError(body: unknown): unknown {
  const msg = 'this action needs human approval but could not be queued — please retry';
  return {
    jsonrpc: '2.0',
    id: jsonRpcIdOf(body),
    result: {
      content: [{ type: 'text', text: msg }],
      isError: true,
    },
  };
}

/** The JSON-RPC id of a single (non-batch) request body; null otherwise. */
export function jsonRpcIdOf(body: unknown): unknown {
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    return (body as { id?: unknown }).id ?? null;
  }
  return null;
}
