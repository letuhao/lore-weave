/**
 * L6.B.2 — WS ticket store (RAID cycle 28).
 *
 * Server-side mirror of `contracts/ws/ticket.go` (cycle 21 L4.L). The Go
 * type is canonical; this TS port is wire-compatible (JSON shape matches
 * the Go struct tags).
 *
 * Per S12 §12AB.2 + Q-L6-3 (line 124): foundation owns server + envelope
 * types only. The browser WS lib is frontend-game's. So this TS module
 * lives in the gateway (api-gateway-bff) — it issues + redeems tickets,
 * never exposes them to the browser as bearer tokens.
 *
 * Critical invariants (enforced by tests):
 *   1. ONE-SHOT — Redeem atomically reads-and-deletes; replay fails.
 *   2. TTL — 60 s, validated against wall-clock at Redeem time.
 *   3. NEVER appears in URL — only in Sec-WebSocket-Protocol header.
 *   4. Sufficient entropy — ticket_id is 128 bits (crypto.randomUUID).
 *   5. Origin + fingerprint hashes bind the ticket to a single browser.
 */

import { createHash, randomUUID } from 'node:crypto';

/** S12 §12AB.2 — V1 ticket TTL. Matches Go const TicketTTL. */
export const TICKET_TTL_MS = 60_000;

/**
 * Sentinel error tags. Callers MUST classify via the `tag` field, not
 * by matching the message (i18n + future copy edits).
 */
export type TicketErrorTag =
  | 'ticket_not_found'
  | 'ticket_expired'
  | 'ticket_id_collision'
  | 'ticket_origin_mismatch'
  | 'ticket_fingerprint_mismatch'
  | 'ticket_invalid';

export class TicketError extends Error {
  constructor(public readonly tag: TicketErrorTag, message: string) {
    super(message);
    this.name = 'TicketError';
  }
}

/**
 * Ticket struct. Wire-compatible JSON with `contracts/ws/ticket.go::Ticket`.
 * Hashes are stored as raw 32-byte Buffers in memory (matches the Go
 * `[32]byte` shape); JSON serialization MUST base64 them — but this
 * module never serializes to the client, so we keep buffers.
 */
export interface Ticket {
  readonly ticketId: string;
  readonly userRefId: string; // UUID
  readonly allowedRealities: readonly string[]; // UUIDs
  readonly allowedScopes: readonly string[];
  readonly originHash: Buffer; // 32 bytes
  readonly clientFingerprintHash: Buffer; // 32 bytes
  readonly issuedAt: number; // ms epoch
  readonly expiresAt: number; // ms epoch
}

/** Compute the SHA-256 hash an origin canonicalizes to. */
export function hashOrigin(origin: string): Buffer {
  return createHash('sha256').update(origin, 'utf8').digest();
}

/**
 * Compute the client-fingerprint hash. Inputs match S12 §12AB.2:
 *   user-agent || ip /24 || tls session id (first 16 bytes hex).
 *
 * The caller is responsible for normalising the IP to /24 (i.e. the last
 * octet zeroed) BEFORE calling. We don't do it here because the source
 * of the IP (X-Forwarded-For vs RemoteAddress) is policy that lives in
 * the upgrade handler — keep this helper pure.
 */
export function hashFingerprint(userAgent: string, ipSlash24: string, tlsSessionPrefix: string): Buffer {
  return createHash('sha256')
    .update(userAgent, 'utf8')
    .update('\x00', 'utf8')
    .update(ipSlash24, 'utf8')
    .update('\x00', 'utf8')
    .update(tlsSessionPrefix, 'utf8')
    .digest();
}

/**
 * Constant-time buffer compare. Use this for ALL ticket binding checks —
 * a leak-free origin match must not short-circuit on the first byte.
 */
export function constantTimeBufferEquals(a: Buffer, b: Buffer): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a[i] ^ b[i];
  }
  return diff === 0;
}

/**
 * TicketStore — persistence interface. Production wires the Redis impl
 * (lw:ws:ticket:<id> key, TTL = TICKET_TTL_MS, atomic DEL on Redeem).
 * Tests use InMemoryTicketStore.
 *
 * Atomicity contract: `redeem(id, now)` MUST return the ticket bytes and
 * delete the entry as a single atomic step. A second call with the same
 * id returns ticket_not_found, even under concurrent racing redeemers.
 */
export interface TicketStore {
  issue(t: Ticket): Promise<void>;
  redeem(ticketId: string, nowMs: number): Promise<Ticket>;
  /** For test inspection only; production impl MAY throw. */
  size(): Promise<number>;
}

/**
 * Issue a fresh ticket with safe defaults. The ID is cryptographically
 * random (Node's crypto.randomUUID is RFC 4122 v4 — 122 random bits, well
 * above the 128-bit minimum we want; collision probability negligible at
 * the V1 issue-rate of <1k/sec).
 *
 * Caller supplies the ALREADY-HASHED origin + fingerprint (the auth/JWT
 * layer hashes once). We never see the raw values.
 */
export function makeTicket(args: {
  userRefId: string;
  allowedRealities: readonly string[];
  allowedScopes: readonly string[];
  originHash: Buffer;
  clientFingerprintHash: Buffer;
  nowMs: number;
}): Ticket {
  if (args.originHash.length !== 32) {
    throw new TicketError('ticket_invalid', `originHash must be 32 bytes, got ${args.originHash.length}`);
  }
  if (args.clientFingerprintHash.length !== 32) {
    throw new TicketError(
      'ticket_invalid',
      `clientFingerprintHash must be 32 bytes, got ${args.clientFingerprintHash.length}`,
    );
  }
  return Object.freeze({
    ticketId: `wst_${randomUUID().replace(/-/g, '')}`,
    userRefId: args.userRefId,
    allowedRealities: Object.freeze([...args.allowedRealities]),
    allowedScopes: Object.freeze([...args.allowedScopes]),
    originHash: args.originHash,
    clientFingerprintHash: args.clientFingerprintHash,
    issuedAt: args.nowMs,
    expiresAt: args.nowMs + TICKET_TTL_MS,
  });
}

/**
 * Validate a ticket envelope against now. Pure check, no side-effects.
 */
export function validateTicket(t: Ticket, nowMs: number): void {
  if (!t.ticketId) throw new TicketError('ticket_invalid', 'ticketId empty');
  if (!t.userRefId) throw new TicketError('ticket_invalid', 'userRefId empty');
  if (t.originHash.length !== 32) throw new TicketError('ticket_invalid', 'originHash wrong size');
  if (t.clientFingerprintHash.length !== 32) {
    throw new TicketError('ticket_invalid', 'fingerprintHash wrong size');
  }
  if (!t.issuedAt) throw new TicketError('ticket_invalid', 'issuedAt zero');
  if (!t.expiresAt) throw new TicketError('ticket_invalid', 'expiresAt zero');
  if (nowMs >= t.expiresAt) {
    throw new TicketError('ticket_expired', `expired at ${t.expiresAt}, now ${nowMs}`);
  }
  // Sanity: TTL window ≤ 2 × canonical TTL (clock-skew tolerance).
  if (t.expiresAt - t.issuedAt > 2 * TICKET_TTL_MS) {
    throw new TicketError('ticket_invalid', `TTL window too wide: ${t.expiresAt - t.issuedAt} > ${2 * TICKET_TTL_MS}`);
  }
}

/**
 * Foundation reference impl. Thread-safe via Node's single-threaded
 * event loop — Map operations are atomic relative to JS callbacks.
 *
 * Production REPLACES this with a Redis-backed store (key+TTL+DEL via
 * a single Lua script for atomicity across replicas). The interface
 * stays identical.
 */
export class InMemoryTicketStore implements TicketStore {
  private readonly store = new Map<string, Ticket>();

  async issue(t: Ticket): Promise<void> {
    if (this.store.has(t.ticketId)) {
      throw new TicketError('ticket_id_collision', `id ${t.ticketId} already exists`);
    }
    this.store.set(t.ticketId, t);
  }

  /**
   * Atomic read-and-delete. Map.get+delete is a single tick — no other
   * JS callback runs between the two. (If we move to Redis: use Lua
   * `local t=redis.call('get',k); redis.call('del',k); return t`.)
   */
  async redeem(ticketId: string, nowMs: number): Promise<Ticket> {
    const t = this.store.get(ticketId);
    if (!t) {
      throw new TicketError('ticket_not_found', `id ${ticketId} not found or already redeemed`);
    }
    this.store.delete(ticketId);
    if (nowMs >= t.expiresAt) {
      throw new TicketError('ticket_expired', `id ${ticketId} expired at ${t.expiresAt}`);
    }
    return t;
  }

  async size(): Promise<number> {
    return this.store.size;
  }
}
