import {
  RedisTicketStore,
  ticketToWire,
  ticketFromWire,
  TICKET_KEY_PREFIX,
  type RedisLike,
} from './redis-ticket-store';
import { TICKET_TTL_MS, TicketError, type Ticket } from './ticket-store';

/**
 * In-process fake of the minimal RedisLike surface: SET-NX + the Lua GET+DEL
 * redeem. Models the one-shot atomicity the store relies on (the real Lua
 * correctness against a live Redis is the deferred D-GAME-WS-LIVE-SMOKE).
 */
class FakeRedis implements RedisLike {
  readonly map = new Map<string, string>();
  async set(key: string, value: string, _px: 'PX', _ttlMs: number, _nx: 'NX'): Promise<string | null> {
    if (this.map.has(key)) return null; // NX → collision
    this.map.set(key, value);
    return 'OK';
  }
  async eval(_script: string, _n: number, key: string): Promise<unknown> {
    const v = this.map.get(key);
    if (v === undefined) return null;
    this.map.delete(key); // GET+DEL
    return v;
  }
}

const GOLDEN_ORIGIN = Buffer.from(Array.from({ length: 32 }, (_, i) => i)); // bytes 0..31
const GOLDEN_FP = Buffer.alloc(32, 0xff); // 32 × 0xFF

function fixtureTicket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    ticketId: 'wst_golden',
    userRefId: '11111111-1111-1111-1111-111111111111',
    allowedRealities: ['22222222-2222-2222-2222-222222222222'],
    allowedScopes: ['chat', 'presence'],
    originHash: GOLDEN_ORIGIN,
    clientFingerprintHash: GOLDEN_FP,
    issuedAt: 1000,
    expiresAt: 1000 + TICKET_TTL_MS,
    ...overrides,
  };
}

describe('RedisTicketStore wire form (132 cross-impl golden fixture)', () => {
  // The CANONICAL base64 (StdEncoding) of bytes 0..31 — the same literal the
  // game-server mirror + the Go contracts/ws test must produce. Pins the
  // shared wire contract so a StdEncoding-vs-URLEncoding drift is caught.
  const ORIGIN_B64_GOLDEN = 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=';

  it('serializes origin_hash to the canonical StdEncoding base64 literal', () => {
    expect(ticketToWire(fixtureTicket()).originHash).toBe(ORIGIN_B64_GOLDEN);
  });

  it('uses StdEncoding (+//), NOT base64url (-_)', () => {
    // 32×0xFF base64-Std contains "/" and never "_" — the explicit Std-vs-URL
    // distinguisher (Node Buffer.from is lenient and would mask a wrong variant).
    const fp = ticketToWire(fixtureTicket()).clientFingerprintHash;
    expect(fp).toContain('/');
    expect(fp).not.toContain('_');
    expect(fp).not.toContain('-');
  });

  it('round-trips hashes byte-for-byte', () => {
    const back = ticketFromWire(ticketToWire(fixtureTicket()));
    expect(back.originHash.equals(GOLDEN_ORIGIN)).toBe(true);
    expect(back.clientFingerprintHash.equals(GOLDEN_FP)).toBe(true);
    expect(back.ticketId).toBe('wst_golden');
    expect(back.allowedScopes).toEqual(['chat', 'presence']);
  });

  it('rejects a wire ticket whose hash is not 32 bytes', () => {
    const bad = { ...ticketToWire(fixtureTicket()), originHash: Buffer.alloc(31).toString('base64') };
    expect(() => ticketFromWire(bad)).toThrow(TicketError);
  });
});

describe('RedisTicketStore issue/redeem', () => {
  it('issues then redeems one-shot (2nd redeem → not_found)', async () => {
    const redis = new FakeRedis();
    const store = new RedisTicketStore(redis);
    const t = fixtureTicket({ issuedAt: Date.now(), expiresAt: Date.now() + TICKET_TTL_MS });
    await store.issue(t);
    expect(redis.map.has(TICKET_KEY_PREFIX + t.ticketId)).toBe(true);

    const got = await store.redeem(t.ticketId, Date.now());
    expect(got.userRefId).toBe(t.userRefId);
    expect(got.originHash.equals(GOLDEN_ORIGIN)).toBe(true);

    await expect(store.redeem(t.ticketId, Date.now())).rejects.toMatchObject({ tag: 'ticket_not_found' });
  });

  it('rejects an id collision on issue (NX)', async () => {
    const store = new RedisTicketStore(new FakeRedis());
    const t = fixtureTicket({ issuedAt: Date.now(), expiresAt: Date.now() + TICKET_TTL_MS });
    await store.issue(t);
    await expect(store.issue(t)).rejects.toMatchObject({ tag: 'ticket_id_collision' });
  });

  it('rejects redeem of an expired ticket (wall-clock authoritative)', async () => {
    const store = new RedisTicketStore(new FakeRedis());
    const t = fixtureTicket({ issuedAt: 1000, expiresAt: 1000 + TICKET_TTL_MS });
    await store.issue(t);
    await expect(store.redeem(t.ticketId, t.expiresAt + 1)).rejects.toMatchObject({ tag: 'ticket_expired' });
  });

  it('rejects a non-positive TTL at issue', async () => {
    const store = new RedisTicketStore(new FakeRedis());
    await expect(store.issue(fixtureTicket({ issuedAt: 5000, expiresAt: 5000 }))).rejects.toMatchObject({
      tag: 'ticket_invalid',
    });
  });
});
