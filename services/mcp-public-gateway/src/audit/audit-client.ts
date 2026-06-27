import { Logger } from '@nestjs/common';
import { loadConfig } from '../config/config.js';
import { firstMethod, toolCallNames } from '../scope/scope-filter.js';

/** One per-key call audit row (H-O) — the wire shape the auth-service ingest accepts. */
export interface McpAuditRow {
  key_id: string;
  owner_user_id: string;
  method: string;
  tool_name?: string | null;
  outcome: 'relayed' | 'denied_scope' | 'rate_limited' | 'unauthorized' | 'upstream_error';
  trace_id?: string | null;
}

/**
 * Build the audit rows for one request (pure — unit-tested). One row per `tools/call`
 * (with the tool name); a non-call request that was denied/rate-limited yields a
 * single method-only row; a successfully RELAYED non-call (tools/list, initialize,
 * ping) yields NO rows (noise, not an action).
 */
export function buildAuditRows(
  body: unknown,
  keyId: string,
  ownerUserId: string,
  traceId: string,
  outcome: McpAuditRow['outcome'],
): McpAuditRow[] {
  const names = toolCallNames(body);
  if (names.length > 0) {
    return names.map((name) => ({
      key_id: keyId,
      owner_user_id: ownerUserId,
      method: 'tools/call',
      tool_name: name,
      outcome,
      trace_id: traceId,
    }));
  }
  if (outcome === 'relayed') return [];
  const method = firstMethod(body);
  if (!method) return [];
  return [{ key_id: keyId, owner_user_id: ownerUserId, method, tool_name: null, outcome, trace_id: traceId }];
}

/**
 * Fire-and-forget audit emitter (H-O). The edge sees every external-agent call and
 * records a best-effort trail in auth-service (`POST /internal/mcp-keys/audit`). It
 * NEVER blocks or throws into the request path — an audit failure must not affect the
 * agent's response (best-effort, like the resolve `last_used_at` write). Audit rows
 * are dropped on any error.
 */
export class AuditClient {
  private readonly cfg = loadConfig();
  private readonly log = new Logger(AuditClient.name);

  /**
   * Emit audit rows for a request, fire-and-forget. One row per `tools/call`
   * (with the tool name); a non-call request that was denied/rate-limited yields a
   * single method-only row. A successfully RELAYED non-call (tools/list, initialize,
   * ping) is NOT audited — that's noise, not an action.
   */
  record(
    body: unknown,
    keyId: string,
    ownerUserId: string,
    traceId: string,
    outcome: McpAuditRow['outcome'],
  ): void {
    const rows = buildAuditRows(body, keyId, ownerUserId, traceId, outcome);
    if (rows.length === 0) return;
    // Detach: do not await. Swallow every error so the response path is untouched.
    void this.send(rows).catch((e) => this.log.debug(`audit emit dropped: ${e}`));
  }

  private async send(rows: McpAuditRow[]): Promise<void> {
    if (!this.cfg.internalToken) return; // cannot authenticate to auth-service
    // Bound the detached fetch: under a hard auth-service hang, an unbounded
    // fire-and-forget POST would accumulate sockets/memory. 2s is generous for an
    // intra-cluster INSERT; on timeout the row is simply dropped (best-effort).
    const res = await fetch(`${this.cfg.authServiceUrl}/internal/mcp-keys/audit`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-internal-token': this.cfg.internalToken },
      body: JSON.stringify(rows),
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) this.log.debug(`audit ingest non-OK: ${res.status}`);
  }
}
