/**
 * L6.A.2 — HTTP → WS upgrade handler (RAID cycle 28).
 *
 * Per S12 §12AB.2 step 2: the ticket NEVER appears in URL query string.
 * Browsers carry it in `Sec-WebSocket-Protocol: lw.v1, ticket.<id>`.
 *
 * This module is a PURE PARSER — no I/O. The NestJS gateway wires it
 * into its connection callback and routes the parsed `UpgradeRequest`
 * to the ticket-store + session-store.
 */

import type { IncomingMessage } from 'node:http';

import { hashOrigin, hashFingerprint } from './ticket-store';

/** Sub-protocol the client claims first. Versioning marker for V2 wire breaks. */
export const PROTOCOL_VERSION = 'lw.v1';

/** Prefix the second protocol token carries. */
export const TICKET_PROTOCOL_PREFIX = 'ticket.';

export interface UpgradeRequest {
  readonly ticketId: string;
  readonly originHeader: string;
  readonly originHash: Buffer;
  readonly fingerprintHash: Buffer;
  readonly userAgent: string;
  readonly clientIpSlash24: string;
}

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

/**
 * Reduce a client IPv4/IPv6 to the privacy-preserving /24 (v4) or /48
 * (v6) prefix used as one component of the fingerprint hash.
 *
 * **Why /24 not raw IP:** an exact-IP fingerprint breaks NAT'd / mobile
 * users who legitimately roam. A /24 (v4) or /48 (v6) covers
 * carrier-grade NAT pools while still tying the ticket to a region —
 * matches S12 §12AB.2 step 3.
 */
export function ipToPrivacyPrefix(ip: string): string {
  // IPv4 — strip last octet.
  const v4 = /^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}$/.exec(ip);
  if (v4) return `${v4[1]}.0`;
  // IPv6 — keep first 3 hextets (effectively /48).
  if (ip.includes(':')) {
    const parts = ip.split(':');
    while (parts.length < 8 && parts.indexOf('') !== -1) parts.splice(parts.indexOf(''), 0, '0');
    return `${parts.slice(0, 3).join(':')}::`;
  }
  // Unknown / loopback / unix sock — return as-is so callers can
  // detect & fail closed if they want strict binding.
  return ip;
}

/**
 * Extract the ticket id from the `Sec-WebSocket-Protocol` request header.
 * Header format MUST be one of:
 *   - "lw.v1, ticket.<id>"
 *   - "lw.v1,ticket.<id>"   (whitespace optional per RFC 7230 §3.2.6)
 *
 * Anything else throws `invalid_protocol_header`. Anything WITH the right
 * outer shape but a missing id throws `missing_ticket`.
 */
export function extractTicketId(rawHeader: string | string[] | undefined): string {
  if (!rawHeader) {
    throw new UpgradeError('invalid_protocol_header', 'Sec-WebSocket-Protocol header missing');
  }
  const flat = Array.isArray(rawHeader) ? rawHeader.join(',') : rawHeader;
  const tokens = flat.split(',').map((t) => t.trim()).filter((t) => t.length > 0);
  if (tokens.length < 2) {
    throw new UpgradeError(
      'invalid_protocol_header',
      `expected 'lw.v1, ticket.<id>' — got ${JSON.stringify(flat)}`,
    );
  }
  if (tokens[0] !== PROTOCOL_VERSION) {
    throw new UpgradeError(
      'invalid_protocol_header',
      `protocol version mismatch: want ${PROTOCOL_VERSION}, got ${tokens[0]}`,
    );
  }
  const ticketToken = tokens[1];
  if (!ticketToken.startsWith(TICKET_PROTOCOL_PREFIX)) {
    throw new UpgradeError(
      'invalid_protocol_header',
      `second protocol token must start with '${TICKET_PROTOCOL_PREFIX}'`,
    );
  }
  const ticketId = ticketToken.slice(TICKET_PROTOCOL_PREFIX.length);
  if (!ticketId) {
    throw new UpgradeError('missing_ticket', `ticket id empty after '${TICKET_PROTOCOL_PREFIX}'`);
  }
  return ticketId;
}

/**
 * Parse a raw IncomingMessage into an UpgradeRequest. The TLS session
 * id input is optional — in plain-HTTP dev mode it's empty string.
 * Production gateway sees terminated TLS via ALB / Envoy → session id
 * comes from the proxy header.
 */
export function parseUpgradeRequest(
  req: IncomingMessage,
  opts: { trustedProxy?: boolean; tlsSessionId?: string } = {},
): UpgradeRequest {
  const ticketId = extractTicketId(req.headers['sec-websocket-protocol']);

  const origin = (req.headers.origin as string | undefined) ?? '';
  if (!origin) {
    throw new UpgradeError('missing_origin', 'Origin header required for WS upgrade');
  }
  const userAgent = (req.headers['user-agent'] as string | undefined) ?? '';
  if (!userAgent) {
    throw new UpgradeError('missing_user_agent', 'User-Agent header required for fingerprint');
  }

  // Trusted-proxy header chain.
  let clientIp = req.socket.remoteAddress ?? '';
  if (opts.trustedProxy) {
    const xff = (req.headers['x-forwarded-for'] as string | undefined) ?? '';
    if (xff) clientIp = xff.split(',')[0].trim();
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
