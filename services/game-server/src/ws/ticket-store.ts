/**
 * WS ticket REDEEM mirror (077 / D-GAME-WS-EDGE-CONTROLS).
 *
 * The game-server is a SEPARATE public WS entry point (PRR-20); clients connect
 * directly. It REDEEMS gateway-issued tickets from the shared Redis store, then
 * validates + binds them. It NEVER issues (the gateway's ticket-endpoint does).
 *
 * Wire-compatible with the Go canonical `contracts/ws/ticket.go` (post-068
 * Hash32 base64) + the gateway's `api-gateway-bff/src/ws/{ticket-store,
 * redis-ticket-store}.ts`. Drift across the three impls is guarded by the shared
 * GOLDEN fixture (132): a fixed 32-byte digest → known base64 (StdEncoding)
 * literal, asserted identically in each impl's tests. (Node `Buffer.from` is
 * lenient and decodes both base64 variants, so only an explicit literal catches
 * a StdEncoding-vs-URLEncoding drift.)
 */
import { createHash } from 'node:crypto';

/** Canonical V1 ticket TTL (matches Go TicketTTL + gateway TICKET_TTL_MS). */
export const TICKET_TTL_MS = 60_000;

/** Redis key namespace (matches the gateway's RedisTicketStore). */
export const TICKET_KEY_PREFIX = 'lw:ws:ticket:';

/** Atomic one-shot GET+DEL (matches the gateway's REDEEM_LUA byte-for-byte). */
export const REDEEM_LUA =
  "local t=redis.call('GET',KEYS[1]); if t then redis.call('DEL',KEYS[1]) end; return t";

export type TicketErrorTag =
  | 'ticket_not_found'
  | 'ticket_expired'
  | 'ticket_origin_mismatch'
  | 'ticket_fingerprint_mismatch'
  | 'ticket_invalid';

export class TicketError extends Error {
  constructor(public readonly tag: TicketErrorTag, message: string) {
    super(message);
    this.name = 'TicketError';
  }
}

/** Ticket — hashes as 32-byte Buffers (matches the Go [32]byte / gateway shape). */
export interface Ticket {
  readonly ticketId: string;
  readonly userRefId: string;
  readonly allowedRealities: readonly string[];
  readonly allowedScopes: readonly string[];
  readonly originHash: Buffer;
  readonly clientFingerprintHash: Buffer;
  readonly issuedAt: number;
  readonly expiresAt: number;
}

/** JSON shape stored in Redis (hashes base64-StdEncoding). */
export interface TicketWire {
  ticketId: string;
  userRefId: string;
  allowedRealities: string[];
  allowedScopes: string[];
  originHash: string;
  clientFingerprintHash: string;
  issuedAt: number;
  expiresAt: number;
}

/** SHA-256 of the canonicalized origin (matches the gateway's hashOrigin). */
export function hashOrigin(origin: string): Buffer {
  return createHash('sha256').update(origin, 'utf8').digest();
}

/**
 * SHA-256 over user-agent || \x00 || ip/24 || \x00 || tls-session-prefix.
 * IP MUST be normalized to /24 by the caller BEFORE this (policy lives in the
 * upgrade path). Byte-for-byte identical to the gateway's hashFingerprint so the
 * binding check matches the issuer's hash.
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

/** Leak-free constant-time buffer compare (for all binding checks). */
export function constantTimeBufferEquals(a: Buffer, b: Buffer): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a[i] ^ b[i];
  return diff === 0;
}

/** Parse a Redis JSON wire ticket (base64 → 32-byte Buffer; rejects bad length). */
export function ticketFromWire(w: TicketWire): Ticket {
  const originHash = Buffer.from(w.originHash ?? '', 'base64');
  const clientFingerprintHash = Buffer.from(w.clientFingerprintHash ?? '', 'base64');
  if (originHash.length !== 32 || clientFingerprintHash.length !== 32) {
    throw new TicketError(
      'ticket_invalid',
      `redis ticket hash wrong size after base64 decode (origin=${originHash.length}, fp=${clientFingerprintHash.length})`,
    );
  }
  return {
    ticketId: w.ticketId,
    userRefId: w.userRefId,
    allowedRealities: Object.freeze([...(w.allowedRealities ?? [])]),
    allowedScopes: Object.freeze([...(w.allowedScopes ?? [])]),
    originHash,
    clientFingerprintHash,
    issuedAt: w.issuedAt,
    expiresAt: w.expiresAt,
  };
}

/** Shape + expiry validation (mirrors the gateway's validateTicket). */
export function validateTicket(t: Ticket, nowMs: number): void {
  if (!t.ticketId) throw new TicketError('ticket_invalid', 'ticketId empty');
  if (!t.userRefId) throw new TicketError('ticket_invalid', 'userRefId empty');
  if (t.originHash.length !== 32) throw new TicketError('ticket_invalid', 'originHash wrong size');
  if (t.clientFingerprintHash.length !== 32) throw new TicketError('ticket_invalid', 'fingerprintHash wrong size');
  if (!t.issuedAt) throw new TicketError('ticket_invalid', 'issuedAt zero');
  if (!t.expiresAt) throw new TicketError('ticket_invalid', 'expiresAt zero');
  if (nowMs >= t.expiresAt) throw new TicketError('ticket_expired', `expired at ${t.expiresAt}, now ${nowMs}`);
  if (t.expiresAt - t.issuedAt > 2 * TICKET_TTL_MS) {
    throw new TicketError('ticket_invalid', `TTL window too wide: ${t.expiresAt - t.issuedAt}`);
  }
}

/**
 * Strict binding: the redeemed ticket's bound hashes MUST match the ones the
 * game-server recomputes from the live upgrade (origin header + UA||ip/24||tls).
 * Constant-time. Throws origin/fingerprint mismatch → close 4007/4009.
 */
export function bindTicket(t: Ticket, originHash: Buffer, fingerprintHash: Buffer): void {
  if (!constantTimeBufferEquals(t.originHash, originHash)) {
    throw new TicketError('ticket_origin_mismatch', 'origin hash mismatch');
  }
  if (!constantTimeBufferEquals(t.clientFingerprintHash, fingerprintHash)) {
    throw new TicketError('ticket_fingerprint_mismatch', 'fingerprint hash mismatch');
  }
}

/** Minimal Redis surface for redeem — structurally satisfied by ioredis. */
export interface RedisLike {
  eval(script: string, numkeys: number, key: string): Promise<unknown>;
}

/**
 * Redeem-only Redis ticket store (the game-server never issues). Atomic one-shot
 * GET+DEL via Lua; a second redeem of the same id returns ticket_not_found.
 */
export class RedisTicketRedeemer {
  constructor(private readonly redis: RedisLike) {}

  async redeem(ticketId: string, nowMs: number): Promise<Ticket> {
    const raw = await this.redis.eval(REDEEM_LUA, 1, TICKET_KEY_PREFIX + ticketId);
    if (raw === null || raw === undefined) {
      throw new TicketError('ticket_not_found', `id ${ticketId} not found or already redeemed`);
    }
    const wire = JSON.parse(
      typeof raw === 'string' ? raw : Buffer.from(raw as Uint8Array).toString('utf8'),
    ) as TicketWire;
    const t = ticketFromWire(wire);
    if (nowMs >= t.expiresAt) {
      throw new TicketError('ticket_expired', `id ${ticketId} expired at ${t.expiresAt}`);
    }
    validateTicket(t, nowMs);
    return t;
  }
}
