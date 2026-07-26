/**
 * WS connection-lifecycle audit (077 control #3).
 *
 * Honest V1 interim: structured-JSON log lines (one per lifecycle event) — an
 * auditable stand-in. The durable event-stream sink (publisher / meta audit) is
 * deferred (D-WS-AUDIT-EVENT-STREAM); the game-server is TS (no Go MetaWrite
 * path) and a V1 metrics/event surface isn't wired yet. The Sink is injectable
 * so a real emitter swaps in without touching the call sites.
 */

import { log } from '../log.js';

export type WsAuditEvent =
  | { kind: 'ws.connection.opened'; connectionId: string; userRefId: string; at: number }
  | { kind: 'ws.connection.closed'; connectionId: string; userRefId: string; reason: string; at: number }
  | { kind: 'ws.handshake.rejected'; reason: string; closeCode: number; at: number };

export interface WsAuditSink {
  emit(event: WsAuditEvent): void;
}

/**
 * Default sink: one structured JSON line per event (stdout). Stable top-level
 * keys (`audit`, `service`) so a log pipeline can route on them. P2·A2b — the
 * default writer is the shared `log.line` JSON-line sink (not bare console.*);
 * still injectable so a real emitter swaps in.
 */
export class LogWsAuditSink implements WsAuditSink {
  constructor(private readonly out: (line: string) => void = (line) => log.line(line)) {}

  emit(event: WsAuditEvent): void {
    this.out(JSON.stringify({ audit: 'ws', service: 'game-server', ...event }));
  }
}
