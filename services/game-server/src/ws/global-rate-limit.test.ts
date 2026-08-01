import { test } from 'node:test';
import assert from 'node:assert/strict';

import { GlobalRateLimiter, globalRateLimitFromEnv, DEFAULT_GLOBAL_RATE_LIMIT } from './global-rate-limit.js';

// CNC-Q1 / CNC-F7. These drive a REAL Redis when LW_TEST_REDIS_URL is set,
// because the whole point of the change is atomicity across processes and an
// in-memory fake would assert the property it is meant to test. Without a
// Redis they still cover the degrade path, which is the branch most likely to
// be wrong and least likely to be exercised in production until it matters.

const URL = process.env.LW_TEST_REDIS_URL;

test('degrades to allowed (not open, not closed) when Redis is unreachable', async () => {
  // Kill-mutation: returning allowed=false here turns a cache outage into a
  // total play outage; returning allowed=true WITHOUT the `degraded` marker
  // hides that the global cap silently stopped enforcing.
  const broken = { eval: async () => { throw new Error('ECONNREFUSED'); } } as never;
  const rl = new GlobalRateLimiter(broken);
  const d = await rl.take('u1', Date.now());
  assert.equal(d.allowed, true, 'a Redis outage must not stop play');
  assert.ok(d.degraded, 'and it must be VISIBLE that the global cap is not enforcing');
  assert.equal(d.remaining, -1);
});

test('config: positive env overrides only', () => {
  process.env.LW_WS_GLOBAL_BURST = '0';       // invalid → ignored
  process.env.LW_WS_GLOBAL_REFILL_PER_SEC = '9';
  const c = globalRateLimitFromEnv();
  assert.equal(c.capacity, DEFAULT_GLOBAL_RATE_LIMIT.capacity, '0 is not a valid burst');
  assert.equal(c.refillPerSec, 9);
  delete process.env.LW_WS_GLOBAL_BURST;
  delete process.env.LW_WS_GLOBAL_REFILL_PER_SEC;
});

test('live Redis: the bucket is shared across INSTANCES (the CNC-F7 fix)', { skip: !URL }, async () => {
  const { default: Redis } = await import('ioredis');
  const redis = new Redis(URL!);
  const user = `test-${Date.now()}-${Math.random()}`;
  const cfg = { capacity: 5, refillPerSec: 0 }; // no refill → a hard budget

  // TWO limiter instances = two replicas. The budget must be shared; if each
  // kept its own count, both would allow 5 and the fleet would allow 10.
  const a = new GlobalRateLimiter(redis, cfg);
  const b = new GlobalRateLimiter(redis, cfg);
  const now = Date.now();

  let allowed = 0;
  for (let i = 0; i < 10; i++) {
    const rl = i % 2 === 0 ? a : b;
    if ((await rl.take(user, now)).allowed) allowed++;
  }
  assert.equal(allowed, 5, 'two replicas share ONE budget of 5, not 5 each');

  await redis.quit();
});

test('live Redis: tokens refill over time', { skip: !URL }, async () => {
  const { default: Redis } = await import('ioredis');
  const redis = new Redis(URL!);
  const user = `test-refill-${Date.now()}-${Math.random()}`;
  const rl = new GlobalRateLimiter(redis, { capacity: 2, refillPerSec: 10 });

  const t0 = Date.now();
  assert.equal((await rl.take(user, t0)).allowed, true);
  assert.equal((await rl.take(user, t0)).allowed, true);
  assert.equal((await rl.take(user, t0)).allowed, false, 'budget exhausted');

  // 500 ms at 10/s = 5 tokens, clamped to capacity 2.
  assert.equal((await rl.take(user, t0 + 500)).allowed, true, 'refilled with elapsed time');

  // Kill-mutation: a clock that goes backwards must not SUBTRACT tokens and
  // lock out a blameless user.
  const back = await rl.take(user, t0 - 10_000);
  assert.ok(back.remaining >= 0, 'a backwards clock never drives the bucket negative');

  await redis.quit();
});
