/**
 * WS connection-lifecycle audit (077 control #3).
 *
 * Honest V1 interim: structured-JSON log lines (one per lifecycle event) — an
 * auditable stand-in. The durable event-stream sink (publisher / meta audit) is
 * deferred (D-WS-AUDIT-EVENT-STREAM); the game-server is TS (no Go MetaWrite
 * path) and a V1 metrics/event surface isn't wired yet. The Sink is injectable
 * so a real emitter swaps in without touching the call sites.
 */

export type WsAuditEvent =
  | { kind: 'ws.connection.opened'; connectionId: string; userRefId: string; at: number }
  | { kind: 'ws.connection.closed'; connectionId: string; userRefId: string; reason: string; at: number }
  | { kind: 'ws.handshake.rejected'; reason: string; closeCode: number; at: number };

export interface WsAuditSink {
  emit(event: WsAuditEvent): void;
}

/**
 * Default sink: one structured JSON line per event (stdout). Stable top-level
 * keys (`audit`, `service`) so a log pipeline can route on them.
 */
export class LogWsAuditSink implements WsAuditSink {
  constructor(private readonly out: (line: string) => void = (line) => console.log(line)) {}

  emit(event: WsAuditEvent): void {
    this.out(JSON.stringify({ audit: 'ws', service: 'game-server', ...event }));
  }
}
