/**
 * WS upgrade parser (077) — game-server mirror of the gateway's
 * `api-gateway-bff/src/ws/upgrade-handler.ts`. PURE (no I/O).
 *
 * The game-server recomputes the origin + fingerprint hashes from the live
 * upgrade so it can BIND the redeemed ticket to this exact connection. The
 * hashing MUST match the issuer (the gateway) byte-for-byte — same
 * `extractTicketId`, same `ipToPrivacyPrefix`, same XFF-first IP derivation,
 * same `hashOrigin`/`hashFingerprint` (imported from ./ticket-store, already a
 * mirror of the gateway) — or every binding check would fail.
 *
 * Input here is Colyseus's `AuthContext` shape ({headers, ip}) rather than a
 * raw IncomingMessage, but the derivation is identical to the gateway's.
 */
import type { IncomingHttpHeaders } from 'node:http';

import { hashOrigin, hashFingerprint } from './ticket-store.js';

/** Sub-protocol the client claims first (V2 wire-break marker). */
export const PROTOCOL_VERSION = 'lw.v1';
/** Prefix the second protocol token carries. */
export const TICKET_PROTOCOL_PREFIX = 'ticket.';

export type UpgradeParseError =
  | 'invalid_protocol_header'
  | 'missing_ticket'
  | 'missing_origin'
  | 'missing_user_agent';

export class UpgradeError extends Error {
  constructor(public readonly tag: UpgradeParseError, message: string) {
    super(message);
    this.name = 'UpgradeError';
  }
}

export interface UpgradeRequest {
  readonly ticketId: string;
  readonly originHeader: string;
  readonly originHash: Buffer;
  readonly fingerprintHash: Buffer;
  readonly userAgent: string;
  readonly clientIpSlash24: string;
}

/**
 * Reduce a client IPv4/IPv6 to the /24 (v4) or /48 (v6) prefix used as one
 * fingerprint component. Byte-identical to the gateway's ipToPrivacyPrefix.
 */
export function ipToPrivacyPrefix(ip: string): string {
  const v4 = /^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}$/.exec(ip);
  if (v4) return `${v4[1]}.0`;
  if (ip.includes(':')) {
    const parts = ip.split(':');
    while (parts.length < 8 && parts.indexOf('') !== -1) parts.splice(parts.indexOf(''), 0, '0');
    return `${parts.slice(0, 3).join(':')}::`;
  }
  return ip;
}

/** Extract the ticket id from `Sec-WebSocket-Protocol: lw.v1, ticket.<id>`. */
export function extractTicketId(rawHeader: string | string[] | undefined): string {
  if (!rawHeader) {
    throw new UpgradeError('invalid_protocol_header', 'Sec-WebSocket-Protocol header missing');
  }
  const flat = Array.isArray(rawHeader) ? rawHeader.join(',') : rawHeader;
  const tokens = flat
    .split(',')
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
  if (tokens.length < 2) {
    throw new UpgradeError('invalid_protocol_header', `expected 'lw.v1, ticket.<id>' — got ${JSON.stringify(flat)}`);
  }
  if (tokens[0] !== PROTOCOL_VERSION) {
    throw new UpgradeError('invalid_protocol_header', `protocol version mismatch: want ${PROTOCOL_VERSION}, got ${tokens[0]}`);
  }
  const ticketToken = tokens[1];
  if (!ticketToken.startsWith(TICKET_PROTOCOL_PREFIX)) {
    throw new UpgradeError('invalid_protocol_header', `second token must start with '${TICKET_PROTOCOL_PREFIX}'`);
  }
  const ticketId = ticketToken.slice(TICKET_PROTOCOL_PREFIX.length);
  if (!ticketId) {
    throw new UpgradeError('missing_ticket', `ticket id empty after '${TICKET_PROTOCOL_PREFIX}'`);
  }
  return ticketId;
}

/** Pick the first X-Forwarded-For token, handling the string|string[] header shape. */
function firstXff(xff: string | string[] | undefined): string {
  if (!xff) return '';
  const flat = Array.isArray(xff) ? xff[0] : xff;
  return flat.split(',')[0]?.trim() ?? '';
}

/**
 * Parse Colyseus AuthContext-style inputs into an UpgradeRequest. Derives the
 * client IP the SAME way the gateway issuer did: trusted-proxy → first
 * X-Forwarded-For token, else the connection IP — so the /24 (and thus the
 * fingerprint) matches.
 */
export function parseUpgrade(
  headers: IncomingHttpHeaders,
  ip: string | string[],
  opts: { trustedProxy?: boolean; tlsSessionId?: string } = {},
): UpgradeRequest {
  const ticketId = extractTicketId(headers['sec-websocket-protocol']);

  const origin = (headers.origin as string | undefined) ?? '';
  if (!origin) throw new UpgradeError('missing_origin', 'Origin header required for WS upgrade');
  const userAgent = (headers['user-agent'] as string | undefined) ?? '';
  if (!userAgent) throw new UpgradeError('missing_user_agent', 'User-Agent header required for fingerprint');

  let clientIp = Array.isArray(ip) ? ip[0] ?? '' : ip;
  if (opts.trustedProxy) {
    const xff = firstXff(headers['x-forwarded-for']);
    if (xff) clientIp = xff;
  }
  const ipSlash24 = ipToPrivacyPrefix(clientIp);
  const tlsSessionPrefix = (opts.tlsSessionId ?? '').slice(0, 32);

  return {
    ticketId,
    originHeader: origin,
    originHash: hashOrigin(origin),
    fingerprintHash: hashFingerprint(userAgent, ipSlash24, tlsSessionPrefix),
    userAgent,
    clientIpSlash24: ipSlash24,
  };
}
