/**
 * ioredis → RateLimitStore adapter. The ONLY place the `ioredis` driver is
 * imported in the edge — the RateLimiter depends on the abstract RateLimitStore
 * interface so it stays driver-free + unit-testable without a real Redis.
 *
 * Config-gated: built only when REDIS_URL is set. Unset → null → the limiter
 * runs in DISABLED (fail-open) mode (dev / single-node convenience).
 */
import Redis from 'ioredis';

import type { RateLimitStore } from './rate-limiter.js';

class RedisRateLimitStore implements RateLimitStore {
  constructor(private readonly redis: Redis) {}

  // INCRBY + (set TTL only on first write) in one round-trip. We always (re)assert
  // EXPIRE NX so a window key can never become immortal if a prior EXPIRE was lost.
  async incrByWithTtl(key: string, by: number, ttlSeconds: number): Promise<number> {
    const results = await this.redis
      .multi()
      .incrby(key, by)
      .expire(key, ttlSeconds, 'NX')
      .exec();
    // results: [[err, incrValue], [err, expireValue]]
    if (!results || results[0]?.[0]) {
      throw results?.[0]?.[0] ?? new Error('redis multi returned no result');
    }
    return Number(results[0][1]);
  }
}

/**
 * Build a RateLimitStore from REDIS_URL, or null when unset (→ limiter disabled).
 * The client connects lazily; a connection error surfaces from incrWithTtl and is
 * mapped to the limiter's fail-open(read)/fail-closed(write) policy.
 */
export function makeRateLimitStoreFromEnv(): RateLimitStore | null {
  const url = process.env.REDIS_URL;
  if (!url) return null;
  const redis = new Redis(url, {
    // Don't let a slow/dead Redis hang the request — fail fast into the policy.
    maxRetriesPerRequest: 1,
    commandTimeout: 1000,
    enableOfflineQueue: false,
    lazyConnect: false,
  });
  // Swallow connection-level errors (they also surface per-command); without a
  // listener ioredis would emit an unhandled 'error' and crash the process.
  redis.on('error', () => undefined);
  return new RedisRateLimitStore(redis);
}
