/**
 * L6.D.3 — WS forced-disconnect dispatcher (RAID cycle 29).
 *
 * Pure logic that closes the WebSockets the supplied gateway has open for
 * a given user_ref_id. The actual Redis pubsub consumer is in
 * `control_channel_consumer.ts`; this module is the in-process action.
 *
 * Idempotency: closing an already-closed socket is a no-op; double-signal
 * with the same nonce is collapsed by the consumer's de-dupe LRU.
 *
 * Close-code semantics: callers MUST pass one of the 11 canonical codes
 * from `crates/contracts-ws/src/close_codes.rs` (mirrored in
 * `contracts/ws/envelope.go::CloseCode`). The TS gateway accepts the raw
 * u16 because cycle 28 ws-server.ts already speaks them.
 */
import type { WsV1Gateway } from './ws-server';

/** Canonical close codes — mirrors the Rust + Go enums for type safety. */
export const FORCE_DISCONNECT_CODES = {
  TOKEN_REVOKED: 4002,
  USER_ERASED: 4003,
  REALITY_ARCHIVED: 4004,
  ADMIN_KICK: 4005,
  FINGERPRINT_MISMATCH: 4009,
} as const;
export type ForceDisconnectCode = (typeof FORCE_DISCONNECT_CODES)[keyof typeof FORCE_DISCONNECT_CODES];

/** Defensive whitelist — any unrecognized close code rejected. */
const VALID_CODES = new Set<number>([1000, 4001, 4002, 4003, 4004, 4005, 4006, 4007, 4008, 4009, 4010]);

export interface DisconnectRequest {
  readonly userRefId: string;
  readonly closeCode: number;
  /** Short string surfaced in the close-frame text (e.g., 'logout', 'admin_kick'). */
  readonly reason: string;
}

export interface DisconnectResult {
  readonly userRefId: string;
  readonly socketsClosed: number;
  readonly closeCode: number;
  /** True iff the request was accepted; false on input validation failure. */
  readonly accepted: boolean;
  readonly rejectReason?: 'unknown_user' | 'invalid_close_code' | 'empty_user_ref';
}

/**
 * `Disconnector` wraps a gateway reference. Production wiring binds the
 * singleton `WsV1Gateway`; tests inject a stub with the same surface.
 */
export interface DisconnectorTarget {
  disconnectUser(userRefId: string, closeCode: number, reasonCode: string): number;
}

export class Disconnector {
  constructor(private readonly target: DisconnectorTarget) {}

  /**
   * Execute the disconnect. Validates input THEN delegates to the gateway.
   * Returns a structured result so the caller (Redis consumer) can emit
   * the right metric label.
   */
  apply(req: DisconnectRequest): DisconnectResult {
    if (!req.userRefId) {
      return {
        userRefId: req.userRefId,
        socketsClosed: 0,
        closeCode: req.closeCode,
        accepted: false,
        rejectReason: 'empty_user_ref',
      };
    }
    if (!VALID_CODES.has(req.closeCode)) {
      return {
        userRefId: req.userRefId,
        socketsClosed: 0,
        closeCode: req.closeCode,
        accepted: false,
        rejectReason: 'invalid_close_code',
      };
    }
    const reasonCode = (req.reason || 'forced').slice(0, 120);
    const count = this.target.disconnectUser(req.userRefId, req.closeCode, reasonCode);
    return {
      userRefId: req.userRefId,
      socketsClosed: count,
      closeCode: req.closeCode,
      accepted: true,
      rejectReason: count === 0 ? 'unknown_user' : undefined,
    };
  }
}

/**
 * Adapter — wraps a real `WsV1Gateway` so the consumer module doesn't
 * import the Nest decorators-laden file directly (cuts test surface).
 */
export function adaptGateway(gw: Pick<WsV1Gateway, 'disconnectUser'>): DisconnectorTarget {
  return {
    disconnectUser: (u, c, r) => gw.disconnectUser(u, c, r),
  };
}
