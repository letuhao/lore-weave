/**
 * L6.A.6 — WebSocket server runtime configuration (RAID cycle 28).
 *
 * Per Q-L6-2 (OPEN_QUESTIONS_LOCKED.md §8 line 118): V1 connection cap = 10 000
 * per replica. HPA scales replicas; the absolute number is verified by load
 * test. The cap is enforced atomically in `ws-server.ts` via a single counter
 * + Mutex-free CAS (Node is single-threaded for event-loop concerns).
 *
 * Per Q-L6-1 (line 117): WS impl extends the existing NestJS api-gateway-bff
 * (matches I1 gateway invariant + LoreWeave novel-platform code). No sidecar.
 *
 * **NO secrets in defaults.** Operational tuning ENV vars only.
 */
export const WS_MAX_CONNECTIONS_PER_REPLICA = 10_000;

/**
 * Upper bound on a single frame's byte length. Defends against memory
 * exhaustion via giant message. 64 KiB matches the V1 chat-payload budget
 * (S12 §12AB.5). Larger payloads (e.g. blob handoffs) MUST go through the
 * separate object-storage upload path, not WS.
 */
export const WS_MAX_MESSAGE_BYTES = 64 * 1024;

/**
 * Keepalive / heartbeat ping interval. Server sends a `ws.ping` every
 * 30 s; clients that miss two consecutive pongs (90 s grace) are closed
 * with 4001 (token_expired) — per S12 §12AB.7.
 */
export const WS_PING_INTERVAL_MS = 30_000;

/**
 * Handshake timeout — the upgrade must complete (ticket redeemed + session
 * record stored) within this budget. Above it, the server returns 408 and
 * the client retries with a fresh ticket. 5 s matches the L6.A acceptance
 * latency budget (P99 < 50 ms steady-state, 5 s cold-start).
 */
export const WS_HANDSHAKE_TIMEOUT_MS = 5_000;

/**
 * Per-connection inbound message rate-limit (token bucket). Server-side
 * rate-limit lives in cycle-29+ (L6.C); this constant is the soft default
 * the gateway loads at startup so unit tests can deterministically pin
 * behaviour without env-var plumbing.
 */
export const WS_INBOUND_RATE_BUCKET_CAPACITY = 30;
export const WS_INBOUND_RATE_REFILL_PER_SEC = 10;

/**
 * Pull operational tuning from env at boot. Returns a frozen snapshot.
 * The factory pattern lets tests inject overrides without mutating module
 * state.
 *
 * The cap is **bounded** at runtime: env can lower the cap but cannot raise
 * it above WS_MAX_CONNECTIONS_PER_REPLICA (Q-L6-2 lockfile).
 */
export interface WsServerConfig {
  readonly maxConnections: number;
  readonly maxMessageBytes: number;
  readonly pingIntervalMs: number;
  readonly handshakeTimeoutMs: number;
  readonly inboundRateCapacity: number;
  readonly inboundRateRefillPerSec: number;
}

export function loadWsServerConfig(env: NodeJS.ProcessEnv = process.env): WsServerConfig {
  const capEnv = env.WS_MAX_CONNECTIONS;
  let cap = WS_MAX_CONNECTIONS_PER_REPLICA;
  if (capEnv) {
    const parsed = Number.parseInt(capEnv, 10);
    if (!Number.isNaN(parsed) && parsed > 0) {
      // env can LOWER but cannot RAISE above the Q-L6-2 ceiling.
      cap = Math.min(parsed, WS_MAX_CONNECTIONS_PER_REPLICA);
    }
  }

  return Object.freeze({
    maxConnections: cap,
    maxMessageBytes: WS_MAX_MESSAGE_BYTES,
    pingIntervalMs: WS_PING_INTERVAL_MS,
    handshakeTimeoutMs: WS_HANDSHAKE_TIMEOUT_MS,
    inboundRateCapacity: WS_INBOUND_RATE_BUCKET_CAPACITY,
    inboundRateRefillPerSec: WS_INBOUND_RATE_REFILL_PER_SEC,
  });
}
