/**
 * L7 — Redis-backed WS TicketStore (077 / D-GAME-WS-EDGE-CONTROLS).
 *
 * The gateway issues tickets here; the game-server (a SEPARATE service) redeems
 * them — so the store MUST be shared across processes. InMemoryTicketStore
 * (ticket-store.ts) is per-replica and cannot bridge issuer→redeemer; Redis can.
 *
 * Design: this store depends ONLY on the minimal `RedisLike` interface below,
 * never on `ioredis` directly. That keeps the store + its tests free of any
 * hard Redis dependency (testable against an in-process fake); the real ioredis
 * client is constructed at the config-gated wiring edge (ws.module) and injected.
 *
 * Wire form (the cross-impl contract): the ticket is stored as JSON with the
 * two hashes as **base64 (StdEncoding)** — matching the Go canonical
 * `contracts/ws/ticket.go::Hash32` (068) + ws/v1.yaml `format: byte`. The
 * game-server stores/reads the SAME shape; the golden fixture (132) pins it so
 * a StdEncoding-vs-URLEncoding drift across the Go/gateway/game-server impls is
 * caught (Node `Buffer.from` is lenient and would otherwise mask it).
 */

import { type Ticket, type TicketStore, TicketError, validateTicket } from './ticket-store';

/**
 * Minimal Redis surface RedisTicketStore needs — structurally satisfied by an
 * `ioredis` client (`new Redis(url)`). Kept as our own interface so the store
 * has no compile-time ioredis dependency.
 */
export interface RedisLike {
  /** SET key value PX ttlMs NX → 'OK' when set, null when the key already existed. */
  set(key: string, value: string, px: 'PX', ttlMs: number, nx: 'NX'): Promise<string | null>;
  /** EVAL script numkeys key → the bulk-string reply (or null). */
  eval(script: string, numkeys: number, key: string): Promise<unknown>;
}

/** Redis key namespace for WS tickets. */
export const TICKET_KEY_PREFIX = 'lw:ws:ticket:';

/**
 * Atomic one-shot read-and-delete across replicas: GET then DEL in a single
 * server-side step. A second redeem of the same id returns nil → ticket_not_found.
 */
export const REDEEM_LUA =
  "local t=redis.call('GET',KEYS[1]); if t then redis.call('DEL',KEYS[1]) end; return t";

/**
 * JSON shape stored in Redis. Hashes base64 (StdEncoding). NOTE (review LOW-3):
 * these field names are camelCase (TS-native), DISTINCT from the snake_case
 * Go/OpenAPI HTTP wire (`ticket_id`/`origin_hash`…). This is a TS-only Redis
 * representation shared between the gateway (writer) + game-server (reader),
 * which agree; a future Go/Rust Redis redeemer must map field names (tracked
 * with D-WS-REDIS-WIRE-SNAKE-CASE / 140).
 */
export interface TicketWire {
  ticketId: string;
  userRefId: string;
  allowedRealities: string[];
  allowedScopes: string[];
  originHash: string; // base64 (32 raw bytes)
  clientFingerprintHash: string; // base64 (32 raw bytes)
  issuedAt: number; // ms epoch
  expiresAt: number; // ms epoch
}

/** Serialize a Ticket to its Redis JSON wire form (hashes → base64). */
export function ticketToWire(t: Ticket): TicketWire {
  return {
    ticketId: t.ticketId,
    userRefId: t.userRefId,
    allowedRealities: [...t.allowedRealities],
    allowedScopes: [...t.allowedScopes],
    originHash: t.originHash.toString('base64'),
    clientFingerprintHash: t.clientFingerprintHash.toString('base64'),
    issuedAt: t.issuedAt,
    expiresAt: t.expiresAt,
  };
}

/** Parse a Redis JSON wire ticket back to a Ticket (base64 → 32-byte Buffer). */
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

/**
 * Production TicketStore backed by Redis. One-shot atomic redeem via Lua.
 */
export class RedisTicketStore implements TicketStore {
  constructor(private readonly redis: RedisLike) {}

  async issue(t: Ticket): Promise<void> {
    const ttlMs = t.expiresAt - t.issuedAt;
    if (ttlMs <= 0) {
      throw new TicketError('ticket_invalid', 'ticket TTL non-positive at issue');
    }
    // NX so an id collision is detected (returns null) rather than silently
    // overwriting a live ticket; PX sets the TTL so a never-redeemed ticket
    // self-expires (defense-in-depth beyond the wall-clock check at redeem).
    const res = await this.redis.set(
      TICKET_KEY_PREFIX + t.ticketId,
      JSON.stringify(ticketToWire(t)),
      'PX',
      ttlMs,
      'NX',
    );
    if (res === null) {
      throw new TicketError('ticket_id_collision', `id ${t.ticketId} already exists`);
    }
  }

  async redeem(ticketId: string, nowMs: number): Promise<Ticket> {
    const raw = await this.redis.eval(REDEEM_LUA, 1, TICKET_KEY_PREFIX + ticketId);
    if (raw === null || raw === undefined) {
      throw new TicketError('ticket_not_found', `id ${ticketId} not found or already redeemed`);
    }
    const wire = JSON.parse(typeof raw === 'string' ? raw : Buffer.from(raw as Uint8Array).toString('utf8')) as TicketWire;
    const t = ticketFromWire(wire);
    // Wall-clock expiry double-check (Redis PX may lag; redeem is authoritative).
    if (nowMs >= t.expiresAt) {
      throw new TicketError('ticket_expired', `id ${ticketId} expired at ${t.expiresAt}`);
    }
    // Defense-in-depth: the same shape check the gateway applied at issue.
    validateTicket(t, nowMs);
    return t;
  }

  /** Unsupported on the production store (test-only on InMemoryTicketStore). */
  async size(): Promise<number> {
    throw new TicketError('ticket_invalid', 'size() is not supported on RedisTicketStore');
  }
}
