import { RateLimiter, type RateLimitStore } from '../src/ratelimit/rate-limiter.js';

// A fake store with a per-key counter (mirrors INCR) we can drive deterministically.
class FakeStore implements RateLimitStore {
  counts = new Map<string, number>();
  async incrByWithTtl(key: string, by: number): Promise<number> {
    const n = (this.counts.get(key) ?? 0) + by;
    this.counts.set(key, n);
    return n;
  }
}

class ErrorStore implements RateLimitStore {
  async incrByWithTtl(): Promise<number> {
    throw new Error('redis down');
  }
}

const NOW = 1_700_000_000_000; // fixed timestamp so the window is deterministic

describe('RateLimiter', () => {
  it('allows calls up to the limit, blocks the one past it', async () => {
    const rl = new RateLimiter(new FakeStore());
    const rpm = 3;
    for (let i = 1; i <= 3; i++) {
      const r = await rl.check('k1', rpm, false, 1, NOW);
      expect(r.allowed).toBe(true);
      expect(r.remaining).toBe(rpm - i);
    }
    const blocked = await rl.check('k1', rpm, false, 1, NOW);
    expect(blocked.allowed).toBe(false);
    expect(blocked.remaining).toBe(0);
    expect(blocked.limit).toBe(3);
  });

  it('isolates counters per key', async () => {
    const rl = new RateLimiter(new FakeStore());
    await rl.check('a', 1, false, 1, NOW);
    const aBlocked = await rl.check('a', 1, false, 1, NOW);
    const bOk = await rl.check('b', 1, false, 1, NOW);
    expect(aBlocked.allowed).toBe(false);
    expect(bOk.allowed).toBe(true);
  });

  it('rolls to a fresh window (different minute → counter resets)', async () => {
    const rl = new RateLimiter(new FakeStore());
    await rl.check('k', 1, false, 1, NOW);
    expect((await rl.check('k', 1, false, 1, NOW)).allowed).toBe(false);
    // +60s → new window key → allowed again.
    expect((await rl.check('k', 1, false, 1, NOW + 60_000)).allowed).toBe(true);
  });

  it('retryAfter is within (0, 60]', async () => {
    const rl = new RateLimiter(new FakeStore());
    const r = await rl.check('k', 5, false, 1, NOW);
    expect(r.retryAfter).toBeGreaterThan(0);
    expect(r.retryAfter).toBeLessThanOrEqual(60);
  });

  it('floors a non-positive rpm at 1 (never blocks everything by misconfig... but still bounds)', async () => {
    const rl = new RateLimiter(new FakeStore());
    expect((await rl.check('k', 0, false, 1, NOW)).limit).toBe(1);
    expect((await rl.check('k', 0, false, 1, NOW)).allowed).toBe(false); // 2nd call > 1
  });

  it('weights the increment so a batch of N costs N (no per-request bypass)', async () => {
    const rl = new RateLimiter(new FakeStore());
    // rpm=10; a single request weighing 7 (a 7-call batch) consumes 7.
    const first = await rl.check('k', 10, false, 7, NOW);
    expect(first.allowed).toBe(true);
    expect(first.remaining).toBe(3);
    // Another weight-7 batch → 14 > 10 → blocked (would've been allowed if counted as 1).
    const second = await rl.check('k', 10, false, 7, NOW);
    expect(second.allowed).toBe(false);
  });

  it('floors a non-positive weight at 1', async () => {
    const rl = new RateLimiter(new FakeStore());
    const r = await rl.check('k', 5, false, 0, NOW);
    expect(r.remaining).toBe(4); // consumed 1, not 0
  });

  // PUB-8 fail policy on store outage.
  it('fails OPEN for reads when the store errors', async () => {
    const rl = new RateLimiter(new ErrorStore());
    const r = await rl.check('k', 1, false, 1, NOW);
    expect(r.allowed).toBe(true);
  });

  it('fails CLOSED for writes when the store errors', async () => {
    const rl = new RateLimiter(new ErrorStore());
    const r = await rl.check('k', 1, true, 1, NOW);
    expect(r.allowed).toBe(false);
  });

  it('is DISABLED (allow all) when no store is configured', async () => {
    const rl = new RateLimiter(null);
    for (let i = 0; i < 100; i++) {
      expect((await rl.check('k', 1, true, 1, NOW)).allowed).toBe(true);
    }
  });
});
