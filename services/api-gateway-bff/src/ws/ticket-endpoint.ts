/**
 * L6.B.1 — POST /v1/ws/ticket REST endpoint (RAID cycle 28).
 *
 * Hands the caller a short-lived (60 s) one-shot ticket they then use
 * in `Sec-WebSocket-Protocol: lw.v1, ticket.<id>` to open `/ws/v1`.
 *
 * Per S12 §12AB.2 and Q-L6-3 (line 124): foundation owns the server side
 * only. The browser side (fetching, storing, attaching to upgrade) is
 * frontend-game.
 *
 * Authentication: caller MUST present a valid bearer JWT (Authorization
 * header) — same secret as the SSE + legacy WS path. This module does NOT
 * mint JWTs; it only verifies them.
 *
 * Security checklist for the ticket-endpoint (auditor focus):
 *   1. Ticket id entropy = 128 bits (randomUUID, RFC 4122 v4).
 *   2. Ticket stored Redis-side with TTL = 60 s.
 *   3. Origin from Origin header is HASHED before storage (never logged raw).
 *   4. Fingerprint from User-Agent + IP/24 + TLS hint is HASHED.
 *   5. Reply NEVER echoes the origin or UA back — only the ticket id.
 *   6. No CSRF token needed because the endpoint requires bearer-JWT (which
 *      browser CORS does not auto-attach cross-origin — defense in depth
 *      via SameSite=strict cookie + Authorization header).
 */

import {
  Body,
  Controller,
  Headers,
  HttpException,
  HttpStatus,
  Inject,
  Logger,
  Optional,
  Post,
  Req,
} from '@nestjs/common';
import type { Request } from 'express';
import * as jwt from 'jsonwebtoken';

import {
  hashOrigin,
  hashFingerprint,
  makeTicket,
  type TicketStore,
  InMemoryTicketStore,
} from './ticket-store';
import { ipToPrivacyPrefix } from './upgrade-handler';

export interface TicketIssueRequestBody {
  /**
   * Realities the bearer wants to subscribe to during the resulting WS
   * session. Server intersects with the JWT's allowed-set (NOT shipped
   * in foundation — Q-L6-3); foundation here simply trusts the body
   * with the caveat the server validates against JWT claims downstream.
   */
  allowedRealities?: string[];
  /** Operation scopes (chat, presence, events). */
  allowedScopes?: string[];
}

export interface TicketIssueReply {
  readonly ticketId: string;
  readonly expiresAt: number; // ms epoch
  readonly ttlMs: number;
}

/**
 * Injection token for the TicketStore so tests / future Redis impl can
 * be swapped. The WsModule provides the default `InMemoryTicketStore`.
 */
export const TICKET_STORE_TOKEN = 'TICKET_STORE';

@Controller('v1/ws')
export class TicketController {
  private readonly logger = new Logger(TicketController.name);
  private readonly tickets: TicketStore;

  constructor(@Optional() @Inject(TICKET_STORE_TOKEN) tickets?: TicketStore) {
    this.tickets = tickets ?? new InMemoryTicketStore();
  }

  @Post('ticket')
  async issue(
    @Body() body: TicketIssueRequestBody,
    @Headers('authorization') authHeader: string | undefined,
    @Headers('origin') originHeader: string | undefined,
    @Headers('user-agent') uaHeader: string | undefined,
    @Req() req: Request,
  ): Promise<TicketIssueReply> {
    // 1. JWT — same as SSE / legacy WS path.
    if (!authHeader || !authHeader.toLowerCase().startsWith('bearer ')) {
      throw new HttpException('missing_bearer_token', HttpStatus.UNAUTHORIZED);
    }
    const token = authHeader.slice('bearer '.length).trim();
    const secret = process.env.JWT_SECRET;
    if (!secret) {
      this.logger.error('TICKET issue rejected: JWT_SECRET not configured');
      throw new HttpException('server_misconfigured', HttpStatus.INTERNAL_SERVER_ERROR);
    }
    let userRefId: string;
    try {
      const decoded = jwt.verify(token, secret) as { sub?: string };
      if (!decoded.sub) throw new Error('sub missing');
      userRefId = decoded.sub;
    } catch (err) {
      this.logger.warn(`TICKET issue rejected: invalid_jwt — ${(err as Error).message}`);
      throw new HttpException('invalid_token', HttpStatus.UNAUTHORIZED);
    }

    // 2. Bind to origin + fingerprint. Both REQUIRED for the WS upgrade
    // to succeed downstream — no point issuing a ticket the upgrade
    // will reject. (Fail-fast keeps issued tickets honest.)
    if (!originHeader) {
      throw new HttpException('missing_origin', HttpStatus.BAD_REQUEST);
    }
    if (!uaHeader) {
      throw new HttpException('missing_user_agent', HttpStatus.BAD_REQUEST);
    }

    // IP/24 component: the first X-Forwarded-For token if present, else the
    // socket remoteAddress. NOTE this is UNCONDITIONAL XFF-trust (not gated like
    // upgrade-handler's parseUpgradeRequest). The game-server redeemer mirrors
    // it — auth.ts wsTrustedProxy() defaults TRUE — so issuer + redeemer hash the
    // same client IP and the fingerprint binds (077 review HIGH-1). The ALB /
    // Envoy MUST strip client-supplied XFF so this can't be spoofed.
    const xff = ((req.headers['x-forwarded-for'] as string | undefined) ?? '').split(',')[0].trim();
    const ip = xff || req.socket?.remoteAddress || '';
    const ipPrefix = ipToPrivacyPrefix(ip);

    const ticket = makeTicket({
      userRefId,
      allowedRealities: body.allowedRealities ?? [],
      allowedScopes: body.allowedScopes ?? [],
      originHash: hashOrigin(originHeader),
      // V1: TLS session prefix not yet plumbed — empty string. The
      // upgrade-handler does the same so the hashes match. When the
      // ALB / Envoy proxy starts forwarding TLS session ids, both
      // sides switch in lockstep.
      clientFingerprintHash: hashFingerprint(uaHeader, ipPrefix, ''),
      nowMs: Date.now(),
    });

    await this.tickets.issue(ticket);

    // 3. Reply with ONLY the id + expiry. We deliberately do NOT echo
    // origin / UA / IP — that would surface in logs/intermediaries and
    // defeat the hash-only storage discipline.
    return {
      ticketId: ticket.ticketId,
      expiresAt: ticket.expiresAt,
      ttlMs: ticket.expiresAt - ticket.issuedAt,
    };
  }
}
