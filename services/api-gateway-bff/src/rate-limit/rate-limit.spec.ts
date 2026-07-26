import * as jwt from 'jsonwebtoken';
import {
  loadRateLimitConfig,
  isInternalToken,
  isRateLimitExempt,
  clientIp,
  userKeyFor,
  ipKeyFor,
  checkRateLimit,
  makeRateLimitMiddleware,
  RateLimitConfig,
  RateLimitRedis,
  DEFAULT_EDGE_RATE_LIMIT_MAX,
  DEFAULT_EDGE_RATE_LIMIT_IP_MAX,
} from './rate-limit';

const TOKEN = 'internal-secret-token';

function cfg(over: Partial<RateLimitConfig> = {}): RateLimitConfig {
  return Object.freeze({
    enabled: true,
    userMax: 3,
    ipMax: 5,
    windowMs: 60_000,
    internalToken: TOKEN,
    ...over,
  });
}

/** In-memory Redis mirroring RATE_LIMIT_LUA (INCR + first-hit/self-heal PEXPIRE + PTTL). */
class FakeRedis implements RateLimitRedis {
  store = new Map<string, { count: number; expireAt: number }>();
  now = 1_000;
  calls = 0;
  async eval(_s: string, _n: number, key: string, windowMs: number | string): Promise<unknown> {
    this.calls += 1;
    const w = Number(windowMs);
    let e = this.store.get(key);
    if (!e || (e.expireAt !== -1 && this.now >= e.expireAt)) {
      e = { count: 0, expireAt: -1 };
      this.store.set(key, e);
    }
    e.count += 1;
    let ttl = e.expireAt === -1 ? -1 : e.expireAt - this.now;
    if (e.count === 1 || ttl < 0) {
      e.expireAt = this.now + w;
      ttl = w;
    }
    return [e.count, ttl];
  }
}

class ThrowingRedis implements RateLimitRedis {
  async eval(): Promise<unknown> {
    throw new Error('ECONNREFUSED / command timeout');
  }
}

function req(over: Partial<{ path: string; headers: Record<string, string>; ip: string }> = {}) {
  return { path: over.path ?? '/v1/books', headers: over.headers ?? {}, ip: over.ip ?? '10.0.0.1' };
}

function mkRes() {
  const r: any = { statusCode: 0, headers: {}, body: '' };
  r.status = (s: number) => ((r.statusCode = s), r);
  r.set = (k: string, v: string) => ((r.headers[k] = v), r);
  r.end = (b: string) => ((r.body = b), r);
  return r;
}

function bearer(sub: string): string {
  return 'Bearer ' + jwt.sign({ sub }, 'any-secret'); // signature irrelevant (decode only)
}

// ── config ───────────────────────────────────────────────────────────────────
describe('loadRateLimitConfig', () => {
  it('defaults', () => {
    const c = loadRateLimitConfig({});
    expect(c.enabled).toBe(true);
    expect(c.userMax).toBe(DEFAULT_EDGE_RATE_LIMIT_MAX);
    expect(c.ipMax).toBe(DEFAULT_EDGE_RATE_LIMIT_IP_MAX);
    expect(c.windowMs).toBe(60_000);
    expect(c.internalToken).toBe('');
  });
  it('overrides + INTERNAL_SERVICE_TOKEN', () => {
    const c = loadRateLimitConfig({
      EDGE_RATE_LIMIT_MAX: '10',
      EDGE_RATE_LIMIT_IP_MAX: '50',
      EDGE_RATE_LIMIT_WINDOW_S: '30',
      INTERNAL_SERVICE_TOKEN: 'T',
    });
    expect(c.userMax).toBe(10);
    expect(c.ipMax).toBe(50);
    expect(c.windowMs).toBe(30_000);
    expect(c.internalToken).toBe('T');
  });
  it('enabled only false on literal "false"', () => {
    expect(loadRateLimitConfig({ EDGE_RATE_LIMIT_ENABLED: 'false' }).enabled).toBe(false);
    expect(loadRateLimitConfig({ EDGE_RATE_LIMIT_ENABLED: 'nonsense' }).enabled).toBe(true);
  });
});

// ── exemptions (H1/H2 — value match, no client-header bypass) ──────────────────
describe('internal-token / exemptions', () => {
  it('isInternalToken requires a VALUE match, not presence (H1)', () => {
    expect(isInternalToken(req({ headers: { 'x-internal-token': TOKEN } }), cfg())).toBe(true);
    expect(isInternalToken(req({ headers: { 'x-internal-token': 'guess' } }), cfg())).toBe(false);
    expect(isInternalToken(req({ headers: { 'x-internal-token': '' } }), cfg())).toBe(false);
  });
  it('empty configured token ⇒ never internal (any header value fails)', () => {
    expect(
      isInternalToken(req({ headers: { 'x-internal-token': 'anything' } }), cfg({ internalToken: '' })),
    ).toBe(false);
  });
  it('exempts health + value-verified internal only', () => {
    expect(isRateLimitExempt(req({ path: '/health' }), cfg())).toBe(true);
    expect(isRateLimitExempt(req({ path: '/health/ready' }), cfg())).toBe(true);
    expect(isRateLimitExempt(req({ headers: { 'x-internal-token': TOKEN } }), cfg())).toBe(true);
    expect(isRateLimitExempt(req({ headers: { 'x-internal-token': 'nope' } }), cfg())).toBe(false);
  });
  it('does NOT exempt on a client Accept header (H2) or a /stream path (M3)', () => {
    expect(isRateLimitExempt(req({ headers: { accept: 'text/event-stream' } }), cfg())).toBe(false);
    expect(isRateLimitExempt(req({ path: '/v1/books/stream' }), cfg())).toBe(false);
    expect(isRateLimitExempt(req({ path: '/v1/anything/generate' }), cfg())).toBe(false);
  });
});

// ── key derivation (M1/M2) ────────────────────────────────────────────────────
describe('key derivation', () => {
  it('clientIp prefers req.ip (trust-proxy computed), not raw XFF', () => {
    expect(clientIp(req({ ip: '1.2.3.4', headers: { 'x-forwarded-for': '9.9.9.9' } }))).toBe('1.2.3.4');
  });
  it('userKeyFor decodes sub; ipKeyFor always present', () => {
    expect(userKeyFor(req({ headers: { authorization: bearer('u1') } }))).toBe('rl:u:u1');
    expect(userKeyFor(req({}))).toBeNull();
    expect(userKeyFor(req({ headers: { authorization: 'Bearer garbage' } }))).toBeNull();
    expect(ipKeyFor(req({ ip: '1.2.3.4' }))).toBe('rl:ip:1.2.3.4');
  });
});

// ── checkRateLimit ────────────────────────────────────────────────────────────
describe('checkRateLimit', () => {
  it('allows under the limit, denies over with a sane Retry-After', async () => {
    const r = new FakeRedis();
    for (let i = 0; i < 3; i++) expect((await checkRateLimit(r, 'k', 3, 60_000)).allowed).toBe(true);
    const d = await checkRateLimit(r, 'k', 3, 60_000);
    expect(d.allowed).toBe(false);
    expect(d.retryAfterS).toBeGreaterThan(0);
    expect(d.retryAfterS).toBeLessThanOrEqual(60);
  });
  it('fails open on a throwing redis + on an unparseable reply', async () => {
    expect(await checkRateLimit(new ThrowingRedis(), 'k', 1, 1000)).toEqual({ allowed: true, failedOpen: true });
    const weird: RateLimitRedis = { eval: async () => 'nonsense' };
    expect((await checkRateLimit(weird, 'k', 1, 1000)).failedOpen).toBe(true);
  });
  it('window resets after expiry (self-heal keeps a TTL)', async () => {
    const r = new FakeRedis();
    for (let i = 0; i < 4; i++) await checkRateLimit(r, 'k', 3, 60_000);
    expect((await checkRateLimit(r, 'k', 3, 60_000)).allowed).toBe(false);
    r.now += 61_000; // window elapsed
    expect((await checkRateLimit(r, 'k', 3, 60_000)).allowed).toBe(true);
  });
});

// ── middleware ────────────────────────────────────────────────────────────────
describe('makeRateLimitMiddleware', () => {
  const run = (mw: any, request: any) => {
    const res = mkRes();
    let nexted = false;
    return new Promise<{ res: any; nexted: boolean; request: any }>((resolve) => {
      const next = () => {
        nexted = true;
        resolve({ res, nexted, request });
      };
      const origEnd = res.end;
      res.end = (b: string) => {
        origEnd(b);
        resolve({ res, nexted, request });
      };
      mw(request, res, next);
    });
  };

  it('pass-through when redis is null or disabled', async () => {
    expect((await run(makeRateLimitMiddleware(null, cfg()), req())).nexted).toBe(true);
    expect((await run(makeRateLimitMiddleware(new FakeRedis(), cfg({ enabled: false })), req())).nexted).toBe(true);
  });

  it('exempts health + value-verified internal (keeping the header, no Redis touch)', async () => {
    const r = new FakeRedis();
    expect((await run(makeRateLimitMiddleware(r, cfg()), req({ path: '/health' }))).nexted).toBe(true);
    const internal = req({ headers: { 'x-internal-token': TOKEN } });
    const out = await run(makeRateLimitMiddleware(r, cfg()), internal);
    expect(out.nexted).toBe(true);
    expect(r.calls).toBe(0);
    expect(internal.headers['x-internal-token']).toBe(TOKEN);
  });

  it('STRIPS a spoofed (non-matching) x-internal-token and still rate-limits it (H1)', async () => {
    const r = new FakeRedis();
    const spoof = req({ headers: { 'x-internal-token': 'attacker' } });
    const out = await run(makeRateLimitMiddleware(r, cfg()), spoof);
    expect(out.nexted).toBe(true);
    expect(spoof.headers['x-internal-token']).toBeUndefined(); // stripped → not forwarded upstream
    expect(r.calls).toBeGreaterThan(0); // rate-limited, not exempt
  });

  it('a client Accept header does NOT exempt (H2)', async () => {
    const r = new FakeRedis();
    await run(makeRateLimitMiddleware(r, cfg()), req({ headers: { accept: 'text/event-stream' } }));
    expect(r.calls).toBeGreaterThan(0);
  });

  it('429s over the USER limit with Retry-After', async () => {
    const r = new FakeRedis();
    const mw = makeRateLimitMiddleware(r, cfg({ userMax: 2, ipMax: 100 }));
    const u = () => req({ headers: { authorization: bearer('u1') }, ip: '1.1.1.1' });
    expect((await run(mw, u())).nexted).toBe(true);
    expect((await run(mw, u())).nexted).toBe(true);
    const denied = await run(mw, u());
    expect(denied.res.statusCode).toBe(429);
    expect(denied.res.headers['Retry-After']).toBeDefined();
    expect(JSON.parse(denied.res.body)).toMatchObject({ error: 'rate_limited' });
  });

  it('a forged/rotating sub is STILL bounded by the IP cap (M1)', async () => {
    const r = new FakeRedis();
    const mw = makeRateLimitMiddleware(r, cfg({ userMax: 1000, ipMax: 3 }));
    for (let i = 0; i < 3; i++) {
      const out = await run(mw, req({ headers: { authorization: bearer('forged-' + i) }, ip: '9.9.9.9' }));
      expect(out.nexted).toBe(true);
    }
    const denied = await run(mw, req({ headers: { authorization: bearer('forged-x') }, ip: '9.9.9.9' }));
    expect(denied.res.statusCode).toBe(429);
  });

  it('per-key isolation: user A hitting the limit does not affect user B or another IP', async () => {
    const r = new FakeRedis();
    const mw = makeRateLimitMiddleware(r, cfg({ userMax: 1, ipMax: 100 }));
    await run(mw, req({ headers: { authorization: bearer('A') }, ip: '1.1.1.1' }));
    expect((await run(mw, req({ headers: { authorization: bearer('A') }, ip: '1.1.1.1' }))).res.statusCode).toBe(429);
    expect((await run(mw, req({ headers: { authorization: bearer('B') }, ip: '2.2.2.2' }))).nexted).toBe(true);
  });

  it('FAILS OPEN when Redis rejects (down or wedged past commandTimeout)', async () => {
    const out = await run(makeRateLimitMiddleware(new ThrowingRedis(), cfg()), req());
    expect(out.nexted).toBe(true);
    expect(out.res.statusCode).toBe(0); // never 429/500
  });
});
