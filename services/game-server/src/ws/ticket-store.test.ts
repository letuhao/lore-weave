import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  ticketFromWire,
  bindTicket,
  hashFingerprint,
  RedisTicketRedeemer,
  TicketError,
  TICKET_TTL_MS,
  TICKET_KEY_PREFIX,
  type RedisLike,
  type TicketWire,
} from './ticket-store.js';

// The SAME golden literal as the gateway (redis-ticket-store.spec.ts) + the Go
// contracts/ws test: base64 (StdEncoding) of bytes 0..31. Pins the cross-impl
// wire contract so a StdEncoding-vs-URLEncoding drift across the three impls is
// caught (132). Node Buffer.from is lenient, so the explicit literal is the guard.
const ORIGIN_B64_GOLDEN = 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=';
const GOLDEN_ORIGIN = Buffer.from(Array.from({ length: 32 }, (_, i) => i));
const GOLDEN_FP = Buffer.alloc(32, 0xff);

function goldenWire(overrides: Partial<TicketWire> = {}): TicketWire {
  return {
    ticketId: 'wst_golden',
    userRefId: '11111111-1111-1111-1111-111111111111',
    allowedRealities: ['22222222-2222-2222-2222-222222222222'],
    allowedScopes: ['chat', 'presence'],
    originHash: ORIGIN_B64_GOLDEN,
    clientFingerprintHash: GOLDEN_FP.toString('base64'),
    issuedAt: 1000,
    expiresAt: 1000 + TICKET_TTL_MS,
    ...overrides,
  };
}

test('golden fixture: canonical StdEncoding base64 decodes to the exact bytes', () => {
  const t = ticketFromWire(goldenWire());
  assert.ok(t.originHash.equals(GOLDEN_ORIGIN), 'origin = bytes 0..31');
  assert.ok(t.clientFingerprintHash.equals(GOLDEN_FP), 'fp = 0xff*32');
  // Re-encode equals the canonical literal — cross-impl parity with gateway+Go.
  assert.equal(t.originHash.toString('base64'), ORIGIN_B64_GOLDEN);
});

test('rejects a wire ticket whose hash is not 32 bytes', () => {
  assert.throws(
    () => ticketFromWire(goldenWire({ originHash: Buffer.alloc(31).toString('base64') })),
    (e: unknown) => e instanceof TicketError && e.tag === 'ticket_invalid',
  );
});

test('bindTicket: strict origin + fingerprint binding', () => {
  const t = ticketFromWire(goldenWire());
  bindTicket(t, GOLDEN_ORIGIN, GOLDEN_FP); // exact match → no throw
  assert.throws(
    () => bindTicket(t, Buffer.alloc(32, 0x01), GOLDEN_FP),
    (e: unknown) => e instanceof TicketError && e.tag === 'ticket_origin_mismatch',
  );
  assert.throws(
    () => bindTicket(t, GOLDEN_ORIGIN, Buffer.alloc(32, 0x02)),
    (e: unknown) => e instanceof TicketError && e.tag === 'ticket_fingerprint_mismatch',
  );
});

test('hashFingerprint is deterministic + 32 bytes (matches issuer formula)', () => {
  const a = hashFingerprint('UA/1.0', '203.0.113.0', '');
  const b = hashFingerprint('UA/1.0', '203.0.113.0', '');
  assert.ok(a.equals(b));
  assert.equal(a.length, 32);
});

class FakeRedis implements RedisLike {
  readonly map = new Map<string, string>();
  async eval(_script: string, _n: number, key: string): Promise<unknown> {
    const v = this.map.get(key);
    if (v === undefined) return null;
    this.map.delete(key); // GET+DEL
    return v;
  }
}

test('RedisTicketRedeemer: one-shot redeem, then not_found', async () => {
  const redis = new FakeRedis();
  const now = Date.now();
  const wire = goldenWire({ issuedAt: now, expiresAt: now + TICKET_TTL_MS });
  redis.map.set(TICKET_KEY_PREFIX + wire.ticketId, JSON.stringify(wire));
  const r = new RedisTicketRedeemer(redis);

  const t = await r.redeem(wire.ticketId, now);
  assert.equal(t.userRefId, wire.userRefId);
  assert.ok(t.originHash.equals(GOLDEN_ORIGIN));

  await assert.rejects(
    r.redeem(wire.ticketId, now),
    (e: unknown) => e instanceof TicketError && e.tag === 'ticket_not_found',
  );
});

test('RedisTicketRedeemer: expired ticket rejected', async () => {
  const redis = new FakeRedis();
  const wire = goldenWire({ issuedAt: 1000, expiresAt: 1000 + TICKET_TTL_MS });
  redis.map.set(TICKET_KEY_PREFIX + wire.ticketId, JSON.stringify(wire));
  const r = new RedisTicketRedeemer(redis);
  await assert.rejects(
    r.redeem(wire.ticketId, wire.expiresAt + 1),
    (e: unknown) => e instanceof TicketError && e.tag === 'ticket_expired',
  );
});
