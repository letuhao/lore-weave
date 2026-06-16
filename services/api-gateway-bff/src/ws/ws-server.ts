/**
 * L6.A.1 — NestJS WebSocket server with ticket handshake (RAID cycle 28).
 *
 * Per Q-L6-1 (OPEN_QUESTIONS_LOCKED.md §8 line 117): extend the existing
 * NestJS api-gateway-bff. NO new sidecar. The existing legacy gateway
 * (`events.gateway.ts`) — JWT-on-query — stays at path `/ws` for now;
 * this new ticket-based server lives at `/ws/v1` for parallel rollout.
 *
 * Per Q-L6-2 (line 118): connection cap = 10 000 per replica, enforced
 * atomically before the upgrade completes. HPA scales replicas; we never
 * accept past the cap.
 *
 * Per Q-L6-3 (line 124): foundation ships server + envelope only. The
 * browser WS lib is frontend-game's responsibility — we don't ship a TS
 * client here.
 */

import {
  WebSocketGateway,
  WebSocketServer,
  type OnGatewayConnection,
  type OnGatewayDisconnect,
  type OnGatewayInit,
} from '@nestjs/websockets';
import { Inject, Injectable, Logger, Optional } from '@nestjs/common';
import type { Server, WebSocket } from 'ws';
import type { IncomingMessage } from 'node:http';
import { randomUUID } from 'node:crypto';

import {
  type TicketStore,
  TicketError,
  InMemoryTicketStore,
  constantTimeBufferEquals,
} from './ticket-store';
import {
  parseUpgradeRequest,
  UpgradeError,
} from './upgrade-handler';
import { WsMetrics, type EvictionReason, type HandshakeFailureReason } from './metrics';
import { loadWsServerConfig, type WsServerConfig } from './config';
import { routeInbound, ENVELOPE_VERSION, type Envelope } from './session-router';
import {
  InMemoryAuthzProvider,
  PerMessageAuthz,
  type AuthzRequest,
  type SessionAuthzContext,
  type SessionAuthzProvider,
} from './per-message-authz';

export interface ActiveConnection {
  readonly connectionId: string;
  readonly userRefId: string;
  readonly allowedRealities: readonly string[];
  readonly allowedScopes: readonly string[];
  readonly socket: WebSocket;
  readonly openedAtMs: number;
}

/**
 * Stateless helper exposed for unit tests. The Nest gateway delegates
 * the handshake to this so the bulk of the logic is testable without
 * Nest's WebSocket lifecycle.
 *
 * Returns the new connection record OR a structured handshake failure.
 */
export type HandshakeOutcome =
  | { ok: true; connection: ActiveConnection }
  | { ok: false; reason: HandshakeFailureReason; closeCode: number };

export interface HandshakeArgs {
  readonly req: IncomingMessage;
  readonly socket: WebSocket;
  readonly nowMs: number;
}

export interface WsServerDeps {
  readonly tickets: TicketStore;
  readonly metrics: WsMetrics;
  readonly config: WsServerConfig;
  readonly logger?: Pick<Logger, 'log' | 'warn' | 'error'>;
}

/**
 * Performs the ticket handshake atomically. The connection cap check
 * sits BEFORE the ticket redeem so we never burn a one-shot ticket
 * just to reject the upgrade for capacity reasons.
 */
export async function performHandshake(
  deps: WsServerDeps,
  activeCount: number,
  args: HandshakeArgs,
): Promise<HandshakeOutcome> {
  const { tickets, metrics, config } = deps;

  // 1. Capacity gate (Q-L6-2). Atomic vs the caller because Node is
  // single-threaded — caller passes the active count read at the same
  // tick as the upgrade callback.
  if (activeCount >= config.maxConnections) {
    metrics.onHandshakeFailure('cap_reached');
    return { ok: false, reason: 'cap_reached', closeCode: 4008 };
  }

  // 2. Parse upgrade.
  let parsed;
  try {
    parsed = parseUpgradeRequest(args.req, { trustedProxy: true });
  } catch (err) {
    if (err instanceof UpgradeError) {
      metrics.onHandshakeFailure(err.tag === 'missing_ticket' ? 'missing_ticket' : 'invalid_protocol_header');
      return { ok: false, reason: err.tag === 'missing_ticket' ? 'missing_ticket' : 'invalid_protocol_header', closeCode: 4010 };
    }
    metrics.onHandshakeFailure('unknown');
    return { ok: false, reason: 'unknown', closeCode: 4010 };
  }

  // 3. Redeem ticket (one-shot).
  let ticket;
  try {
    ticket = await tickets.redeem(parsed.ticketId, args.nowMs);
  } catch (err) {
    if (err instanceof TicketError) {
      const reason: HandshakeFailureReason = err.tag === 'ticket_expired' ? 'ticket_expired' : 'ticket_redeem_failed';
      metrics.onHandshakeFailure(reason);
      metrics.onTicketRedeem(err.tag === 'ticket_expired' ? 'expired' : 'not_found');
      return { ok: false, reason, closeCode: 4001 };
    }
    metrics.onHandshakeFailure('unknown');
    return { ok: false, reason: 'unknown', closeCode: 4001 };
  }

  // 4. Origin binding (constant-time compare).
  if (!constantTimeBufferEquals(ticket.originHash, parsed.originHash)) {
    metrics.onHandshakeFailure('origin_mismatch');
    metrics.onTicketRedeem('origin_mismatch');
    return { ok: false, reason: 'origin_mismatch', closeCode: 4007 };
  }

  // 5. Fingerprint binding.
  if (!constantTimeBufferEquals(ticket.clientFingerprintHash, parsed.fingerprintHash)) {
    metrics.onHandshakeFailure('fingerprint_mismatch');
    metrics.onTicketRedeem('fingerprint_mismatch');
    return { ok: false, reason: 'fingerprint_mismatch', closeCode: 4009 };
  }

  // 6. All checks pass — issue connection id + record open.
  metrics.onTicketRedeem('success');
  metrics.onConnectionOpen();
  const connection: ActiveConnection = {
    connectionId: randomUUID(),
    userRefId: ticket.userRefId,
    allowedRealities: ticket.allowedRealities,
    allowedScopes: ticket.allowedScopes,
    socket: args.socket,
    openedAtMs: args.nowMs,
  };
  return { ok: true, connection };
}

/**
 * NestJS gateway wrapping the handshake. The internal Map is the only
 * authoritative source of "active connection count" so the cap is
 * enforced consistently.
 *
 * Wired by `WsModule` (cycle 28 extension).
 */
@WebSocketGateway({ path: '/ws/v1' })
@Injectable()
export class WsV1Gateway implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server!: Server;

  private readonly logger = new Logger(WsV1Gateway.name);
  readonly metrics = new WsMetrics();
  readonly config: WsServerConfig = loadWsServerConfig();
  readonly tickets: TicketStore;
  readonly authz: PerMessageAuthz;

  private readonly active = new Map<WebSocket, ActiveConnection>();
  /** Reverse index user_ref_id → set of sockets (L6.D fan-out). */
  private readonly byUser = new Map<string, Set<WebSocket>>();
  private pingInterval?: NodeJS.Timeout;

  constructor(
    @Optional() @Inject('TICKET_STORE') tickets?: TicketStore,
    @Optional() @Inject('AUTHZ_PROVIDER') authzProvider?: SessionAuthzProvider,
  ) {
    // In production the WsModule binds the same InMemoryTicketStore
    // (or future RedisTicketStore) to both this gateway and the
    // TicketController — issue + redeem must share state.
    this.tickets = tickets ?? new InMemoryTicketStore();
    // L6.C (cycle 29): per-message re-authz. Foundation ships the
    // in-memory provider; production swaps in the roleplay-service RPC
    // client. The provider only matters once data messages flow — control
    // frames skip authz via the router fast-path.
    this.authz = new PerMessageAuthz(authzProvider ?? new InMemoryAuthzProvider(), this.metrics);
  }

  afterInit(): void {
    this.pingInterval = setInterval(() => this.heartbeat(), this.config.pingIntervalMs);
    if (this.pingInterval.unref) this.pingInterval.unref();
    this.logger.log(
      `WS /ws/v1 init — cap=${this.config.maxConnections} ping=${this.config.pingIntervalMs}ms`,
    );
  }

  async handleConnection(socket: WebSocket, req: IncomingMessage): Promise<void> {
    const outcome = await performHandshake(
      { tickets: this.tickets, metrics: this.metrics, config: this.config, logger: this.logger },
      this.active.size,
      { req, socket, nowMs: Date.now() },
    );
    if (!outcome.ok) {
      this.logger.warn(`WS /ws/v1 handshake rejected: ${outcome.reason}`);
      socket.close(outcome.closeCode, outcome.reason);
      return;
    }
    this.active.set(socket, outcome.connection);
    this.addToUserIndex(outcome.connection.userRefId, socket);

    socket.on('message', (raw) => this.onInbound(socket, raw));
    this.logger.log(
      `WS /ws/v1 accepted: conn=${outcome.connection.connectionId} user=${outcome.connection.userRefId} active=${this.active.size}`,
    );
  }

  handleDisconnect(socket: WebSocket): void {
    const conn = this.active.get(socket);
    if (conn) {
      this.active.delete(socket);
      this.removeFromUserIndex(conn.userRefId, socket);
      this.metrics.onConnectionClose('normal_close' as EvictionReason);
      this.logger.log(`WS /ws/v1 closed — active=${this.active.size}`);
    }
  }

  /**
   * Inbound message dispatch — delegates to the pure router. ALL inbound
   * frames feed metrics; data frames forward downstream (sink hooked by
   * outbound-fanout / roleplay-service RPC — wiring is cycle-29+).
   */
  private onInbound(socket: WebSocket, raw: unknown): void {
    const conn = this.active.get(socket);
    if (!conn) return; // race: closed mid-read.

    let env: unknown;
    try {
      const text =
        typeof raw === 'string'
          ? raw
          : Buffer.isBuffer(raw)
            ? raw.toString('utf8')
            : Array.isArray(raw)
              ? Buffer.concat(raw as Buffer[]).toString('utf8')
              : String(raw);
      if (text.length > this.config.maxMessageBytes) {
        socket.close(4010, 'schema_invalid');
        return;
      }
      env = JSON.parse(text);
    } catch {
      socket.close(4010, 'schema_invalid');
      return;
    }

    const outcome = routeInbound(env, this.metrics);
    switch (outcome.tag) {
      case 'control_ack':
        if (socket.readyState === socket.OPEN) {
          socket.send(JSON.stringify(outcome.reply));
          this.metrics.onMessage('s2c', outcome.reply.kind);
        }
        return;
      case 'refresh_requested':
        // V1: instruct the client to fetch a new HTTP ticket — the actual
        // refresh handshake lives in cycle 29 (L6.C). For now, send a
        // hint frame.
        if (socket.readyState === socket.OPEN) {
          const hint = {
            v: ENVELOPE_VERSION,
            kind: 'control' as const,
            type: 'ws.refresh.hint',
            dir: 's2c' as const,
          };
          socket.send(JSON.stringify(hint));
          this.metrics.onMessage('s2c', 'control');
        }
        return;
      case 'data_forward':
        // L6.C cycle 29 — re-run S2/S3 authz on EVERY data frame. Without
        // this, a user kicked mid-connection can keep sending until the
        // next handshake (the S2-regression-via-WS class).
        void this.authorizeAndForward(conn, outcome.envelope).catch((err) => {
          // Defense in depth: an authz provider that throws MUST drop the
          // frame, not crash the gateway. The error path here is a bug
          // (provider should return false, not throw) so we count it as a
          // generic schema_invalid for now.
          this.logger.error(`WS /ws/v1 authz error: ${(err as Error)?.message ?? err}`);
          this.metrics.onAuthzReject('schema_invalid');
        });
        return;
      case 'rejected':
        if (outcome.reason === 'schema_invalid') {
          socket.close(4010, 'schema_invalid');
        }
        return;
    }
  }

  /**
   * Heartbeat — fires every config.pingIntervalMs. The browser MUST reply
   * with `ws.pong`; failure to do so for 2 intervals triggers a forced
   * disconnect with code 4001 (cycle-29 L6.D).
   */
  private heartbeat(): void {
    if (this.active.size === 0) return;
    const ping = JSON.stringify({
      v: ENVELOPE_VERSION,
      kind: 'control',
      type: 'ws.ping',
      dir: 's2c',
    });
    for (const [sock] of this.active.entries()) {
      if (sock.readyState === sock.OPEN) {
        sock.send(ping);
        this.metrics.onMessage('s2c', 'control');
      }
    }
  }

  /** Test-only inspection — used by ws-server.spec.ts. */
  /* istanbul ignore next — instrumentation only */
  inspectActiveCount(): number {
    return this.active.size;
  }

  /**
   * Forced disconnect entry-point (L6.D, cycle 29). Closes all live
   * connections belonging to `userRefId` with the supplied close code.
   * Idempotent: closing an already-closed socket is a no-op. Returns the
   * count of sockets that were touched.
   *
   * Called by `WsControlChannelConsumer` on incoming WS-disconnect signals;
   * also callable directly from in-process admin tooling.
   */
  disconnectUser(userRefId: string, closeCode: number, reasonCode: string): number {
    const sockets = this.byUser.get(userRefId);
    if (!sockets || sockets.size === 0) return 0;
    let count = 0;
    // Snapshot the set — `handleDisconnect` removes entries during the close.
    for (const sock of [...sockets]) {
      try {
        const rs = (sock as { readyState?: number }).readyState;
        if (rs === 0 || rs === 1) {
          // CONNECTING (0) or OPEN (1) — close it.
          sock.close(closeCode, reasonCode);
        }
        // CLOSING (2) / CLOSED (3) — already closing; idempotent no-op.
        count += 1;
      } catch (err) {
        this.logger.warn(`WS /ws/v1 force-disconnect close threw: ${(err as Error).message}`);
      }
      // Note: handleDisconnect on the socket fires the 'close' event which
      // calls metrics.onConnectionClose('normal_close'); we override the
      // reason to 'forced_disconnect' here so the metric is accurate.
      this.metrics.onConnectionClose('forced_disconnect' as EvictionReason);
    }
    // Authz cache invalidation — the forced-disconnect SLA assumes the
    // next time this user reconnects, the authz cache for them is empty.
    this.authz.invalidateUser(userRefId);
    return count;
  }

  /**
   * Per-message authz check + downstream forward. Split out of the inbound
   * switch so the hot path stays readable.
   */
  private async authorizeAndForward(conn: ActiveConnection, env: Envelope): Promise<void> {
    const req = buildAuthzRequest(conn, env);
    const outcome = await this.authz.evaluateInbound(req);
    if (outcome.tag === 'deny') {
      // Per S12 §12AB.L3 — drop the frame, increment metric, NEVER
      // tear down the connection (a single bad frame is not connection
      // poisoning — that's the rate-limit path 4006 instead).
      return;
    }
    // Authorized — downstream service wiring is the roleplay-service RPC
    // (cycle 30+). Keep the foundation bisectable: log + count.
    this.metrics.onMessage('c2s', env.kind);
  }

  private addToUserIndex(userRefId: string, sock: WebSocket): void {
    let s = this.byUser.get(userRefId);
    if (!s) {
      s = new Set<WebSocket>();
      this.byUser.set(userRefId, s);
    }
    s.add(sock);
  }

  private removeFromUserIndex(userRefId: string, sock: WebSocket): void {
    const s = this.byUser.get(userRefId);
    if (!s) return;
    s.delete(sock);
    if (s.size === 0) this.byUser.delete(userRefId);
  }
}

/**
 * Pure helper — derives the authz request from a connection + envelope.
 * Exported so unit tests can build the same request shape the gateway
 * passes to PerMessageAuthz.
 *
 * Payload contract (foundation V1, refined by downstream service in cycle
 * 30+): when the envelope payload is an object, we lift `session_id`,
 * `reality_id`, `privacy_level` if present. Unknown / missing fields
 * remain undefined and the authz evaluator handles that gracefully.
 */
export function buildAuthzRequest(conn: ActiveConnection, env: Envelope): AuthzRequest {
  const payload = (env.payload && typeof env.payload === 'object') ? (env.payload as Record<string, unknown>) : {};
  const ctx: SessionAuthzContext = {
    userRefId: conn.userRefId,
    allowedRealities: conn.allowedRealities,
    allowedScopes: conn.allowedScopes,
  };
  return {
    ctx,
    messageType: env.type,
    sessionId: typeof payload.session_id === 'string' ? payload.session_id : undefined,
    realityId: typeof payload.reality_id === 'string' ? payload.reality_id : undefined,
    privacyLevel: typeof payload.privacy_level === 'string' ? payload.privacy_level : undefined,
    requiredScope: requiredScopeForType(env.type),
  };
}

/**
 * Foundation-grade type → scope mapping. Each message type declares one
 * required scope; cycle 30+ moves this to a registry-driven table.
 */
function requiredScopeForType(messageType: string): string | undefined {
  // Convention: dot-separated, first segment = scope name.
  // 'chat.message' → 'chat'; 'session.update' → 'session'; etc.
  const dot = messageType.indexOf('.');
  if (dot <= 0) return undefined;
  return messageType.slice(0, dot);
}
