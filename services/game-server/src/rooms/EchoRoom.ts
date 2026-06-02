import { Room, Client, ServerError, type AuthContext } from 'colyseus';

import {
  ticketRedeemerFromEnv,
  authenticateTicket,
  authCloseCode,
  wsTrustedProxy,
  CLOSE_RATE_LIMIT,
  CLOSE_CONNECTION_LIMIT,
} from '../ws/auth.js';
import {
  ConnectionCap,
  MessageRateLimiter,
  rateLimitsFromEnv,
} from '../ws/rate-limit.js';
import { LogWsAuditSink, type WsAuditSink } from '../ws/audit.js';

// Edge-control singletons (077 #2/#3). Per-replica, like the gateway's caps.
const rateConfig = rateLimitsFromEnv();
const connectionCap = new ConnectionCap(rateConfig.maxConnectionsPerUser);
const auditSink: WsAuditSink = new LogWsAuditSink();
// Per-connection message-rate limiter + the reason a connection is being closed
// (so onLeave audits the real cause), keyed by Colyseus sessionId.
const messageLimiters = new Map<string, MessageRateLimiter>();
const leaveReasons = new Map<string, string>();

// V0 EchoRoom — minimal Colyseus room used by Session E to validate the
// full WebSocket path end-to-end:
//   - auth handshake via onAuth (rejects empty jwt)
//   - bidirectional message via onMessage('echo')
//   - reconnect via Colyseus built-in reconnectionToken
//
// V1+ replaces this with real game rooms (zone instances, combat,
// chat) per spec §17. The pattern of onAuth + onMessage + onDispose
// stays the same; only the message types and state schema grow.

export interface JoinOptions {
  jwt?: string;
  userId?: string;
}

export interface AuthedUser {
  userId: string;
}

// V0 has no shared state schema — Echo is fire-and-forget messages.
// V1+ Rooms will use Colyseus Schema for state sync.
interface EmptyState {}

/**
 * Pure auth check — extracted from EchoRoom so it can be unit-tested
 * without instantiating a full Colyseus Room. Returns the AuthedUser
 * on success; throws ServerError on failure. V1+ replaces the body
 * with real JWT verification against auth-service.
 */
export function authenticate(options: JoinOptions | undefined, expected: string): AuthedUser {
  if (!options?.jwt) {
    throw new ServerError(401, 'missing jwt');
  }
  if (options.jwt !== expected) {
    throw new ServerError(403, 'invalid jwt');
  }
  return { userId: options.userId ?? 'guest' };
}

export function expectedToken(): string {
  return process.env.LOREWEAVE_INTERNAL_TOKEN ?? 'dev_token';
}

export class EchoRoom extends Room<EmptyState, AuthedUser> {
  /**
   * Handshake auth (077, PRR-20 control #1). When a shared Redis ticket store
   * is configured (LW_WS_REDIS_URL), validate a real gateway-issued ticket:
   * parse Sec-WebSocket-Protocol → redeem (one-shot) → validate → bind origin +
   * fingerprint to this connection; reject with the §12AB.9 close code. Unset
   * (dev) → the V0 static-token fallback (NOT for prod exposure).
   */
  async onAuth(_client: Client, options: JoinOptions, context: AuthContext): Promise<AuthedUser> {
    let authed: AuthedUser;
    try {
      const redeemer = ticketRedeemerFromEnv();
      authed = redeemer
        ? {
            userId: (
              await authenticateTicket(redeemer, context.headers, context.ip, Date.now(), {
                trustedProxy: wsTrustedProxy(),
              })
            ).userId,
          }
        : authenticate(options, expectedToken());
    } catch (err) {
      // §12AB.9 close code (origin 4007 / fingerprint 4009 / token 4001 /
      // schema 4010), or the ServerError code from the dev static path.
      const code = err instanceof ServerError ? (err.code as number) : authCloseCode(err);
      auditSink.emit({
        kind: 'ws.handshake.rejected',
        reason: (err as Error).message,
        closeCode: code,
        at: Date.now(),
      });
      throw err instanceof ServerError ? err : new ServerError(code, (err as Error).message);
    }

    // Per-user connection cap (077 #2 / clears 035). CHECK here (reject over-cap
    // with 4008); the slot is ACQUIRED in onJoin + released in onLeave, so it
    // cannot leak on an auth-without-join (review MED-1: onLeave does not fire
    // for a reserved-but-never-joined seat). A small over-count is possible
    // under concurrent handshakes for one user (TOCTOU between this check and
    // onJoin's acquire) — acceptable for an anti-griefing cap.
    if (connectionCap.atCap(authed.userId)) {
      auditSink.emit({
        kind: 'ws.handshake.rejected',
        reason: 'connection_limit_exceeded',
        closeCode: CLOSE_CONNECTION_LIMIT,
        at: Date.now(),
      });
      throw new ServerError(CLOSE_CONNECTION_LIMIT, 'connection limit exceeded');
    }
    return authed;
  }

  onCreate(): void {
    // Reconnect window — clients have 30s after disconnect to call
    // client.reconnect(token) before the server reaps the seat.
    this.setSeatReservationTime(30);

    this.onMessage('echo', (client, message) => {
      // Per-connection message-rate cap (077 #2). Over the window → close 4006.
      const limiter = messageLimiters.get(client.sessionId);
      if (limiter && !limiter.allow(Date.now())) {
        leaveReasons.set(client.sessionId, 'rate_limit_exceeded');
        client.leave(CLOSE_RATE_LIMIT);
        return;
      }
      client.send('echo', {
        original: message,
        receivedAt: Date.now(),
        echoedBy: 'EchoRoom',
        userId: client.auth.userId,
      });
    });
  }

  onJoin(client: Client): void {
    // Acquire the per-user slot HERE (paired with the onLeave release) so it
    // cannot leak on an auth-without-join (review MED-1). The onAuth atCap check
    // already gated over-cap; this acquire is the authoritative count.
    connectionCap.acquire(client.auth.userId);
    messageLimiters.set(
      client.sessionId,
      new MessageRateLimiter(rateConfig.messagesPerWindow, rateConfig.windowMs),
    );
    auditSink.emit({
      kind: 'ws.connection.opened',
      connectionId: client.sessionId,
      userRefId: client.auth.userId,
      at: Date.now(),
    });
    client.send('welcome', {
      userId: client.auth.userId,
      sessionId: client.sessionId,
      reconnectionToken: client.reconnectionToken,
    });
  }

  async onLeave(client: Client, consented: boolean): Promise<void> {
    // Final departure: release the per-user slot, drop the limiter, audit the
    // close with its real reason (rate-limit / consented / disconnect-expired).
    const finalize = (reason: string): void => {
      connectionCap.release(client.auth.userId);
      messageLimiters.delete(client.sessionId);
      leaveReasons.delete(client.sessionId);
      auditSink.emit({
        kind: 'ws.connection.closed',
        connectionId: client.sessionId,
        userRefId: client.auth.userId,
        reason,
        at: Date.now(),
      });
    };

    const pending = leaveReasons.get(client.sessionId);
    if (consented || pending) {
      finalize(pending ?? 'consented');
      return;
    }
    // Non-consented disconnect: hold the slot for the reconnect window.
    try {
      await this.allowReconnection(client, 'manual');
      // Reconnected — keep the slot + limiter.
    } catch {
      finalize('disconnect_expired');
    }
  }
}
