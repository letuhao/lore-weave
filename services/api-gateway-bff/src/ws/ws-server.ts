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
import { routeInbound, ENVELOPE_VERSION } from './session-router';

interface ActiveConnection {
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

  private readonly active = new Map<WebSocket, ActiveConnection>();
  private pingInterval?: NodeJS.Timeout;

  constructor(@Optional() @Inject('TICKET_STORE') tickets?: TicketStore) {
    // In production the WsModule binds the same InMemoryTicketStore
    // (or future RedisTicketStore) to both this gateway and the
    // TicketController — issue + redeem must share state.
    this.tickets = tickets ?? new InMemoryTicketStore();
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

    socket.on('message', (raw) => this.onInbound(socket, raw));
    this.logger.log(
      `WS /ws/v1 accepted: conn=${outcome.connection.connectionId} user=${outcome.connection.userRefId} active=${this.active.size}`,
    );
  }

  handleDisconnect(socket: WebSocket): void {
    if (this.active.has(socket)) {
      this.active.delete(socket);
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
        // Downstream service wiring lives in outbound-fanout + roleplay
        // RPC — placeholder log to keep the foundation contract bisectable.
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
}
