/**
 * L6.D.1 — Redis control-channel consumer (RAID cycle 29).
 *
 * Reads from the shared `lw:dependency:control` Redis pubsub topic (cycle
 * 7 L1.J) and dispatches WS-disconnect kinds to the in-process gateway via
 * `Disconnector`.
 *
 * Why share the channel: avoids a second Redis pubsub subscription per
 * pod, fewer connections to manage, single SRE runbook for control-plane
 * incidents. Non-WS kinds (mode_shift, mode_probe) are ignored cheaply.
 *
 * Idempotency: subscribers de-dupe on `nonce_id` via a small LRU. Two
 * publishers (legit retry; or split-brain) emitting the same disconnect
 * collapse to a single action.
 *
 * Malformed-payload safety: decode errors are logged + counted, NEVER
 * crash the consumer. The Redis client itself handles connection
 * recovery (per the cycle 7 service-mode framework).
 */
import type { Disconnector } from './disconnector';
import type { WsMetrics } from './metrics';

/** Wire schema mirrors `contracts/lifecycle/mode_propagation.go::ControlMessage`. */
export interface RawControlMessage {
  readonly version?: number;
  readonly kind?: string;
  readonly service?: string;
  readonly instance?: string;
  readonly reason?: string;
  readonly ts_nanos?: number;
  readonly user_ref_id?: string;
  readonly close_code?: number;
  readonly nonce_id?: string;
}

export type ConsumeOutcome =
  | { tag: 'dispatched'; socketsClosed: number }
  | { tag: 'duplicate' }
  | { tag: 'ignored'; reason: 'non_ws_kind' | 'unsupported_version' }
  | { tag: 'dropped'; reason: 'malformed_json' | 'invalid_payload' | 'unknown_kind' };

export const SUPPORTED_VERSION = 1;

/** Small LRU — bounded so a flood of unique nonces can't OOM the pod. */
const DEFAULT_DEDUP_CAPACITY = 1024;

export class WsControlChannelConsumer {
  private readonly seenNonces = new Map<string, number>(); // value = insertion order tick
  private tick = 0;

  constructor(
    private readonly disconnector: Disconnector,
    private readonly metrics: WsMetrics,
    private readonly logger?: { warn(msg: string): void; error(msg: string): void },
    private readonly dedupCapacity: number = DEFAULT_DEDUP_CAPACITY,
  ) {}

  /**
   * Process a single raw message from Redis. The pubsub adapter calls this
   * for each delivered message. Returns the structured outcome so the
   * adapter can emit metrics; never throws.
   */
  consume(raw: unknown): ConsumeOutcome {
    let parsed: RawControlMessage;
    if (typeof raw === 'string') {
      try {
        parsed = JSON.parse(raw) as RawControlMessage;
      } catch (err) {
        this.metrics.onAuthzReject('schema_invalid');
        this.logger?.warn(`ws-control: malformed JSON: ${(err as Error).message}`);
        return { tag: 'dropped', reason: 'malformed_json' };
      }
    } else if (raw && typeof raw === 'object') {
      parsed = raw as RawControlMessage;
    } else {
      this.metrics.onAuthzReject('schema_invalid');
      return { tag: 'dropped', reason: 'malformed_json' };
    }

    if (parsed.version !== SUPPORTED_VERSION) {
      // Mixed-version rollouts — log + ignore; new pods will see new versions.
      this.logger?.warn(`ws-control: unsupported version ${parsed.version}`);
      return { tag: 'ignored', reason: 'unsupported_version' };
    }

    // Non-WS kinds (mode_shift, mode_probe) — silent skip.
    if (parsed.kind !== 'ws_disconnect_user') {
      // Recognized non-WS kinds (mode_shift/mode_probe) → ignored cleanly.
      if (parsed.kind === 'mode_shift' || parsed.kind === 'mode_probe') {
        return { tag: 'ignored', reason: 'non_ws_kind' };
      }
      this.logger?.warn(`ws-control: unknown kind ${parsed.kind}`);
      return { tag: 'dropped', reason: 'unknown_kind' };
    }

    // Required-field check — empty user / nonce / close-code rejects.
    if (
      !parsed.user_ref_id ||
      !parsed.nonce_id ||
      typeof parsed.close_code !== 'number' ||
      !parsed.reason
    ) {
      this.metrics.onAuthzReject('schema_invalid');
      this.logger?.warn('ws-control: ws_disconnect_user missing required field');
      return { tag: 'dropped', reason: 'invalid_payload' };
    }

    // Idempotency — same nonce twice collapses.
    if (this.seenNonces.has(parsed.nonce_id)) {
      return { tag: 'duplicate' };
    }
    this.recordNonce(parsed.nonce_id);

    const result = this.disconnector.apply({
      userRefId: parsed.user_ref_id,
      closeCode: parsed.close_code,
      reason: parsed.reason,
    });

    if (!result.accepted) {
      this.metrics.onAuthzReject('schema_invalid');
      this.logger?.warn(`ws-control: disconnector rejected: ${result.rejectReason}`);
      return { tag: 'dropped', reason: 'invalid_payload' };
    }

    return { tag: 'dispatched', socketsClosed: result.socketsClosed };
  }

  /** Test-only — inspect dedup table. */
  /* istanbul ignore next */
  inspectDedupSize(): number {
    return this.seenNonces.size;
  }

  private recordNonce(nonce: string): void {
    this.seenNonces.set(nonce, ++this.tick);
    if (this.seenNonces.size > this.dedupCapacity) {
      // Drop the oldest entry — Map preserves insertion order in JS.
      const oldest = this.seenNonces.keys().next();
      if (!oldest.done) this.seenNonces.delete(oldest.value);
    }
  }
}

/**
 * Canonical Redis pubsub topic name — mirrors
 * `contracts/lifecycle/mode_propagation.go::ControlChannel`. Exported so
 * the IoC binding code uses the single constant.
 */
export const WS_CONTROL_REDIS_CHANNEL = 'lw:dependency:control';
