/**
 * WS handshake ticket authentication for the game-server (077, control #1).
 *
 * Config-gated: when LW_WS_REDIS_URL is set, the room authenticates a real
 * gateway-issued ticket — parse the Sec-WebSocket-Protocol header → redeem
 * (one-shot) from the shared Redis store → validate shape/expiry → bind the
 * origin + fingerprint to THIS connection. Unset (dev) → the caller falls back
 * to the V0 static-token path.
 *
 * `authenticateTicket` is dependency-injected (takes a `TicketRedeemer`), so it
 * is unit-tested with a fake redeemer + synthetic headers — no Redis needed.
 */
import Redis from 'ioredis';
import type { IncomingHttpHeaders } from 'node:http';

import {
  RedisTicketRedeemer,
  validateTicket,
  bindTicket,
  TicketError,
  type Ticket,
  type RedisLike,
} from './ticket-store.js';
import { parseUpgrade, UpgradeError } from './upgrade.js';

export interface AuthedUser {
  userId: string;
  userRefId: string;
  allowedRealities: readonly string[];
  allowedScopes: readonly string[];
}

// §12AB.9 close codes (subset relevant to the edge) — mirror contracts/ws.
export const CLOSE_TOKEN_EXPIRED = 4001;
export const CLOSE_RATE_LIMIT = 4006;
export const CLOSE_ORIGIN_MISMATCH = 4007;
export const CLOSE_CONNECTION_LIMIT = 4008;
export const CLOSE_FINGERPRINT_MISMATCH = 4009;
export const CLOSE_SCHEMA_INVALID = 4010;

/** Map a redemption/parse failure to its §12AB.9 WS close code. */
export function authCloseCode(err: unknown): number {
  if (err instanceof TicketError) {
    switch (err.tag) {
      case 'ticket_origin_mismatch':
        return CLOSE_ORIGIN_MISMATCH;
      case 'ticket_fingerprint_mismatch':
        return CLOSE_FINGERPRINT_MISMATCH;
      case 'ticket_not_found':
      case 'ticket_expired':
        return CLOSE_TOKEN_EXPIRED;
      default:
        return CLOSE_SCHEMA_INVALID;
    }
  }
  // Malformed/absent Sec-WebSocket-Protocol, origin, UA, etc.
  if (err instanceof UpgradeError) return CLOSE_SCHEMA_INVALID;
  return CLOSE_SCHEMA_INVALID;
}

/** The redeem surface authenticateTicket needs (real or fake). */
export interface TicketRedeemer {
  redeem(ticketId: string, nowMs: number): Promise<Ticket>;
}

/**
 * Authenticate a handshake: parse the upgrade, redeem the ticket one-shot,
 * validate, and bind origin + fingerprint to this connection. Throws
 * TicketError / UpgradeError on any failure (caller → authCloseCode + reject).
 */
export async function authenticateTicket(
  redeemer: TicketRedeemer,
  headers: IncomingHttpHeaders,
  ip: string | string[],
  nowMs: number,
  opts: { trustedProxy?: boolean; tlsSessionId?: string } = {},
): Promise<AuthedUser> {
  const up = parseUpgrade(headers, ip, opts);
  const ticket = await redeemer.redeem(up.ticketId, nowMs);
  validateTicket(ticket, nowMs);
  bindTicket(ticket, up.originHash, up.fingerprintHash);
  return {
    userId: ticket.userRefId,
    userRefId: ticket.userRefId,
    allowedRealities: ticket.allowedRealities,
    allowedScopes: ticket.allowedScopes,
  };
}

/**
 * Whether to trust X-Forwarded-For for the client IP. Defaults TRUE to MIRROR
 * the gateway ISSUER (ticket-endpoint.ts derives ip = xff||remoteAddress
 * unconditionally) + the gateway's own redeemer (ws-server.ts hardcodes
 * trustedProxy:true) — so issuer + redeemer hash the SAME client IP and the
 * fingerprint binds. (review HIGH-1: a gated default-OFF would 4009 EVERY
 * handshake in prod, where the ALB always sets XFF.) Set LW_WS_TRUSTED_PROXY=0
 * ONLY for direct, no-proxy local testing. In prod the ALB/Envoy MUST strip
 * client-supplied XFF (else a client could spoof the IP component).
 */
export function wsTrustedProxy(): boolean {
  return process.env.LW_WS_TRUSTED_PROXY !== '0';
}

/**
 * Fail-closed config gate for the PUBLIC WS boundary (review HIGH-2). The
 * static-token dev fallback (onAuth when no Redis store) must NEVER run on a
 * public prod deploy. Call before listening: throws when NODE_ENV=production
 * and no shared ticket store is configured (LW_WS_REDIS_URL unset), unless dev
 * auth is consciously allowed via LW_WS_ALLOW_DEV_AUTH=1.
 */
export function assertWsAuthConfig(env: NodeJS.ProcessEnv = process.env): void {
  const prod = env.NODE_ENV === 'production';
  const hasRedis = !!env.LW_WS_REDIS_URL;
  const allowDev = env.LW_WS_ALLOW_DEV_AUTH === '1';
  if (prod && !hasRedis && !allowDev) {
    throw new Error(
      'game-server: refusing to start — NODE_ENV=production with no LW_WS_REDIS_URL means ' +
        'WS ticket validation is OFF and onAuth would fall back to static dev_token auth on a ' +
        'PUBLIC boundary. Set LW_WS_REDIS_URL, or LW_WS_ALLOW_DEV_AUTH=1 to consciously override.',
    );
  }
}

let cachedRedeemer: RedisTicketRedeemer | null | undefined;

/**
 * Config-gated redeemer singleton: a RedisTicketRedeemer when LW_WS_REDIS_URL
 * is set, else null (→ the room uses the V0 static-token dev path). ioredis is
 * imported here (the only driver import); the client is constructed only when
 * the URL is present, so dev/test stay Redis-free.
 */
export function ticketRedeemerFromEnv(): RedisTicketRedeemer | null {
  if (cachedRedeemer !== undefined) return cachedRedeemer;
  const url = process.env.LW_WS_REDIS_URL;
  cachedRedeemer = url ? new RedisTicketRedeemer(new Redis(url) as unknown as RedisLike) : null;
  return cachedRedeemer;
}
