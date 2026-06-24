/**
 * L6.E.1 — WebSocket metrics emission (RAID cycle 28).
 *
 * Foundation-grade in-process counters. We deliberately AVOID a Prometheus
 * client library here (no `prom-client` dep) — the foundation contract is
 * "expose the counters via a typed accessor"; the prom-scrape adapter
 * lives in a sibling cycle (L7 obs runtime). Decoupling lets unit tests
 * read counters directly without a registry side-effect.
 *
 * Cardinality discipline per Q-L6 + I19 (inventory.yaml cardinality_budget):
 *   - lw_ws_active_connections — gauge, NO per-connection label (1 series)
 *   - lw_ws_handshake_failures_total — counter, label = reason (~10 values)
 *   - lw_ws_messages_total — counter, labels = direction (2) × kind (2) (4)
 *   - lw_ws_authz_rejections_total — counter, label = reason (~5 values)
 *   - lw_ws_ticket_redeemed_total — counter, label = outcome (success|expired|notfound|mismatch) (4)
 *   - lw_ws_connection_evictions_total — counter, label = reason (cap|forced|expired) (3)
 *
 * Total bounded series: 1 + 10 + 4 + 5 + 4 + 3 = 27 series per replica.
 * Well within the budget.
 */

export type HandshakeFailureReason =
  | 'missing_ticket'
  | 'invalid_protocol_header'
  | 'ticket_redeem_failed'
  | 'ticket_expired'
  | 'origin_mismatch'
  | 'fingerprint_mismatch'
  | 'cap_reached'
  | 'session_store_failed'
  | 'unknown';

export type AuthzRejectionReason =
  | 's2_not_in_session'
  | 's3_privacy_violation'
  | 'scope_not_allowed'
  | 'reality_not_allowed'
  | 'schema_invalid';

export type TicketRedeemOutcome = 'success' | 'expired' | 'not_found' | 'origin_mismatch' | 'fingerprint_mismatch';

export type EvictionReason = 'cap_reached_lru' | 'forced_disconnect' | 'session_expired' | 'normal_close';

export type Direction = 'c2s' | 's2c';
export type Kind = 'control' | 'data';

interface CounterRecord {
  readonly name: string;
  readonly labels: Readonly<Record<string, string>>;
  readonly value: number;
}

/**
 * Bounded label-keyed counter. The label space is whitelisted via the
 * registerLabels constructor arg — emitting with an unknown label
 * combination throws (V1 inventory-lint behaviour at code-level).
 */
class LabeledCounter {
  private readonly values = new Map<string, number>();
  constructor(
    public readonly name: string,
    private readonly labelKeys: readonly string[],
  ) {}

  inc(labels: Record<string, string>, delta = 1): void {
    const key = this.canonicalKey(labels);
    this.values.set(key, (this.values.get(key) ?? 0) + delta);
  }

  read(labels: Record<string, string>): number {
    return this.values.get(this.canonicalKey(labels)) ?? 0;
  }

  snapshot(): CounterRecord[] {
    const out: CounterRecord[] = [];
    for (const [key, value] of this.values.entries()) {
      const labels = this.parseKey(key);
      out.push({ name: this.name, labels, value });
    }
    return out;
  }

  private canonicalKey(labels: Record<string, string>): string {
    const parts: string[] = [];
    for (const k of this.labelKeys) {
      const v = labels[k];
      if (v === undefined) throw new Error(`metric ${this.name}: missing label ${k}`);
      parts.push(`${k}=${v}`);
    }
    // Reject unknown labels to keep cardinality bounded.
    for (const k of Object.keys(labels)) {
      if (!this.labelKeys.includes(k)) {
        throw new Error(`metric ${this.name}: unknown label ${k}`);
      }
    }
    return parts.join('|');
  }

  private parseKey(key: string): Record<string, string> {
    const out: Record<string, string> = {};
    if (key === '') return out;
    for (const part of key.split('|')) {
      const [k, v] = part.split('=', 2);
      out[k] = v;
    }
    return out;
  }
}

class Gauge {
  private value = 0;
  constructor(public readonly name: string) {}

  inc(delta = 1): void {
    this.value += delta;
  }

  dec(delta = 1): void {
    this.value = Math.max(0, this.value - delta);
  }

  set(v: number): void {
    this.value = v;
  }

  get(): number {
    return this.value;
  }

  snapshot(): CounterRecord {
    return { name: this.name, labels: {}, value: this.value };
  }
}

/**
 * WsMetrics — typed facade over the bounded counter set. Singleton per
 * gateway replica. Tests inject a fresh instance.
 */
export class WsMetrics {
  readonly activeConnections = new Gauge('lw_ws_active_connections');
  readonly handshakeFailures = new LabeledCounter('lw_ws_handshake_failures_total', ['reason']);
  readonly messages = new LabeledCounter('lw_ws_messages_total', ['direction', 'kind']);
  readonly authzRejections = new LabeledCounter('lw_ws_authz_rejections_total', ['reason']);
  readonly ticketRedeemed = new LabeledCounter('lw_ws_ticket_redeemed_total', ['outcome']);
  readonly evictions = new LabeledCounter('lw_ws_connection_evictions_total', ['reason']);

  onHandshakeFailure(reason: HandshakeFailureReason): void {
    this.handshakeFailures.inc({ reason });
  }

  onMessage(direction: Direction, kind: Kind): void {
    this.messages.inc({ direction, kind });
  }

  onAuthzReject(reason: AuthzRejectionReason): void {
    this.authzRejections.inc({ reason });
  }

  onTicketRedeem(outcome: TicketRedeemOutcome): void {
    this.ticketRedeemed.inc({ outcome });
  }

  onConnectionOpen(): void {
    this.activeConnections.inc();
  }

  onConnectionClose(reason: EvictionReason): void {
    this.activeConnections.dec();
    this.evictions.inc({ reason });
  }

  /**
   * Returns the cap-saturation ratio for alert routing. Used by the
   * `infra/prometheus/alerts/ws.yaml` rule via the scrape path; here
   * we expose it as a code-level accessor so the WS server can pre-emptively
   * scale before scrape ticks (P99 saturation alerts page SRE per S12).
   */
  saturationRatio(maxConnections: number): number {
    if (maxConnections <= 0) return 0;
    return this.activeConnections.get() / maxConnections;
  }

  /** Flat dump for testing + future scrape adapter. */
  snapshot(): CounterRecord[] {
    return [
      this.activeConnections.snapshot(),
      ...this.handshakeFailures.snapshot(),
      ...this.messages.snapshot(),
      ...this.authzRejections.snapshot(),
      ...this.ticketRedeemed.snapshot(),
      ...this.evictions.snapshot(),
    ];
  }
}
