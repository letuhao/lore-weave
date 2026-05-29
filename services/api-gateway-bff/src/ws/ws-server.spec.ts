/**
 * L6.A.7 — WS server handshake tests (RAID cycle 28).
 *
 * Acceptance criteria per cycle brief:
 *   - WS server handles ticket-based handshake → session created
 *   - Connection cap = 10 000 per replica (Q-L6-2) — 10001st rejected
 *   - Origin + fingerprint mismatches rejected with correct close codes
 */

import type { IncomingMessage } from 'node:http';
import type { Socket } from 'node:net';

import { performHandshake } from './ws-server';
import {
  hashFingerprint,
  hashOrigin,
  InMemoryTicketStore,
  makeTicket,
  type Ticket,
} from './ticket-store';
import { WsMetrics } from './metrics';
import { loadWsServerConfig, WS_MAX_CONNECTIONS_PER_REPLICA } from './config';
import { extractTicketId, ipToPrivacyPrefix, UpgradeError } from './upgrade-handler';

const ORIGIN = 'https://app.loreweave.dev';
const UA = 'Mozilla/5.0 LoreWeaveTest';

function makeReq(opts: {
  ticketId: string;
  origin?: string;
  ua?: string;
  ip?: string;
  protocolHeader?: string;
}): IncomingMessage {
  const fakeSocket = { remoteAddress: opts.ip ?? '203.0.113.10' } as Partial<Socket>;
  return {
    headers: {
      'sec-websocket-protocol': opts.protocolHeader ?? `lw.v1, ticket.${opts.ticketId}`,
      origin: opts.origin ?? ORIGIN,
      'user-agent': opts.ua ?? UA,
    },
    socket: fakeSocket as Socket,
  } as unknown as IncomingMessage;
}

function makeFakeWebSocket(): any {
  const events: Array<{ code: number; reason: string }> = [];
  return {
    close(code: number, reason: string) {
      events.push({ code, reason });
    },
    send: jest.fn(),
    readyState: 1,
    OPEN: 1,
    inspectCloses(): Array<{ code: number; reason: string }> {
      return events;
    },
  };
}

async function issueValidTicket(store: InMemoryTicketStore, nowMs: number, ip = '203.0.113.10'): Promise<Ticket> {
  const ipPrefix = ipToPrivacyPrefix(ip);
  const t = makeTicket({
    userRefId: '00000000-0000-0000-0000-000000000abc',
    allowedRealities: ['00000000-0000-0000-0000-000000000def'],
    allowedScopes: ['chat'],
    originHash: hashOrigin(ORIGIN),
    clientFingerprintHash: hashFingerprint(UA, ipPrefix, ''),
    nowMs,
  });
  await store.issue(t);
  return t;
}

describe('WsV1Gateway / performHandshake', () => {
  it('Q-L6-2: connection cap = 10 000 per replica (constant)', () => {
    expect(WS_MAX_CONNECTIONS_PER_REPLICA).toBe(10_000);
  });

  it('happy path: ticket → connection accepted', async () => {
    const store = new InMemoryTicketStore();
    const metrics = new WsMetrics();
    const config = loadWsServerConfig({});
    const now = 1_000_000;
    const ticket = await issueValidTicket(store, now);

    const outcome = await performHandshake(
      { tickets: store, metrics, config },
      0,
      { req: makeReq({ ticketId: ticket.ticketId }), socket: makeFakeWebSocket(), nowMs: now },
    );
    expect(outcome.ok).toBe(true);
    if (!outcome.ok) return;
    expect(outcome.connection.userRefId).toBe(ticket.userRefId);
    expect(outcome.connection.allowedRealities).toEqual(ticket.allowedRealities);
    expect(metrics.ticketRedeemed.read({ outcome: 'success' })).toBe(1);
    expect(metrics.activeConnections.get()).toBe(1);
  });

  it('Q-L6-2: rejects 10 001st connection with close code 4008 (cap_reached)', async () => {
    const store = new InMemoryTicketStore();
    const metrics = new WsMetrics();
    const config = loadWsServerConfig({});
    const now = 1_000_000;
    // Issue a ticket so the upgrade would otherwise succeed.
    const ticket = await issueValidTicket(store, now);

    const outcome = await performHandshake(
      { tickets: store, metrics, config },
      // Already at cap → reject immediately, do NOT burn the ticket.
      config.maxConnections,
      { req: makeReq({ ticketId: ticket.ticketId }), socket: makeFakeWebSocket(), nowMs: now },
    );
    expect(outcome).toEqual(
      expect.objectContaining({ ok: false, reason: 'cap_reached', closeCode: 4008 }),
    );
    // Critical: the ticket is NOT burned by a cap-reject.
    expect(await store.size()).toBe(1);
    expect(metrics.handshakeFailures.read({ reason: 'cap_reached' })).toBe(1);
  });

  it('rejects bogus protocol header with 4010 (schema_invalid)', async () => {
    const store = new InMemoryTicketStore();
    const metrics = new WsMetrics();
    const config = loadWsServerConfig({});
    const now = 1_000_000;
    await issueValidTicket(store, now);

    const outcome = await performHandshake(
      { tickets: store, metrics, config },
      0,
      {
        req: makeReq({ ticketId: 'unused', protocolHeader: 'wrong.proto' }),
        socket: makeFakeWebSocket(),
        nowMs: now,
      },
    );
    expect(outcome.ok).toBe(false);
    if (outcome.ok) return;
    expect(outcome.closeCode).toBe(4010);
  });

  it('rejects unknown ticket with 4001 (ticket_redeem_failed)', async () => {
    const store = new InMemoryTicketStore();
    const metrics = new WsMetrics();
    const config = loadWsServerConfig({});

    const outcome = await performHandshake(
      { tickets: store, metrics, config },
      0,
      { req: makeReq({ ticketId: 'wst_doesnotexist' }), socket: makeFakeWebSocket(), nowMs: 1 },
    );
    expect(outcome.ok).toBe(false);
    if (outcome.ok) return;
    expect(outcome.reason).toBe('ticket_redeem_failed');
    expect(outcome.closeCode).toBe(4001);
  });

  it('rejects mismatched origin with 4007', async () => {
    const store = new InMemoryTicketStore();
    const metrics = new WsMetrics();
    const config = loadWsServerConfig({});
    const now = 1_000_000;
    const ticket = await issueValidTicket(store, now);

    const outcome = await performHandshake(
      { tickets: store, metrics, config },
      0,
      {
        req: makeReq({ ticketId: ticket.ticketId, origin: 'https://evil.example' }),
        socket: makeFakeWebSocket(),
        nowMs: now,
      },
    );
    expect(outcome.ok).toBe(false);
    if (outcome.ok) return;
    expect(outcome.closeCode).toBe(4007);
    expect(metrics.handshakeFailures.read({ reason: 'origin_mismatch' })).toBe(1);
  });

  it('rejects mismatched fingerprint with 4009 (different UA)', async () => {
    const store = new InMemoryTicketStore();
    const metrics = new WsMetrics();
    const config = loadWsServerConfig({});
    const now = 1_000_000;
    const ticket = await issueValidTicket(store, now);

    const outcome = await performHandshake(
      { tickets: store, metrics, config },
      0,
      {
        req: makeReq({ ticketId: ticket.ticketId, ua: 'EvilUA/9.9' }),
        socket: makeFakeWebSocket(),
        nowMs: now,
      },
    );
    expect(outcome.ok).toBe(false);
    if (outcome.ok) return;
    expect(outcome.closeCode).toBe(4009);
  });

  it('rejects expired ticket with 4001', async () => {
    const store = new InMemoryTicketStore();
    const metrics = new WsMetrics();
    const config = loadWsServerConfig({});
    const now = 1_000_000;
    const ticket = await issueValidTicket(store, now);

    const outcome = await performHandshake(
      { tickets: store, metrics, config },
      0,
      {
        req: makeReq({ ticketId: ticket.ticketId }),
        socket: makeFakeWebSocket(),
        nowMs: now + 60_000 + 1,
      },
    );
    expect(outcome.ok).toBe(false);
    if (outcome.ok) return;
    expect(outcome.reason).toBe('ticket_expired');
  });
});

describe('upgrade-handler', () => {
  it('extracts ticket id from canonical "lw.v1, ticket.<id>" header', () => {
    expect(extractTicketId('lw.v1, ticket.abc123')).toBe('abc123');
    expect(extractTicketId('lw.v1,ticket.abc123')).toBe('abc123');
  });

  it('rejects header with wrong protocol version', () => {
    expect(() => extractTicketId('lw.v2, ticket.abc')).toThrow(UpgradeError);
  });

  it('rejects header missing ticket prefix', () => {
    expect(() => extractTicketId('lw.v1, bearer.abc')).toThrow(UpgradeError);
  });

  it('rejects header with empty ticket id', () => {
    expect(() => extractTicketId('lw.v1, ticket.')).toThrow(UpgradeError);
  });

  it('rejects missing header', () => {
    expect(() => extractTicketId(undefined)).toThrow(UpgradeError);
  });

  it('ipToPrivacyPrefix zeroes last octet for IPv4', () => {
    expect(ipToPrivacyPrefix('192.168.1.42')).toBe('192.168.1.0');
    expect(ipToPrivacyPrefix('10.0.0.1')).toBe('10.0.0.0');
  });

  it('ipToPrivacyPrefix collapses to /48 for IPv6', () => {
    expect(ipToPrivacyPrefix('2001:db8:abcd:1234::1')).toBe('2001:db8:abcd::');
  });
});
