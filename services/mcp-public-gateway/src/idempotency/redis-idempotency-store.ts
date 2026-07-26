/**
 * ioredis → IdempotencyStore adapter. Mirrors `ratelimit/redis-store.ts`: the
 * service depends on the abstract `IdempotencyStore` so it stays driver-free +
 * unit-testable without a real Redis.
 *
 * Config-gated: built only when REDIS_URL is set. Unset → null → idempotency runs
 * DISABLED (fail-open) — public write retries are not deduped (dev convenience).
 */
import Redis from 'ioredis';

import type { IdempotencyStore } from './idempotency-store.js';

class RedisIdempotencyStore implements IdempotencyStore {
  constructor(private readonly redis: Redis) {}

  async claimOrLoad(
    key: string,
    pendingValue: string,
    ttlSeconds: number,
  ): Promise<{ won: true } | { won: false; value: string }> {
    // SET key pending NX EX ttl → 'OK' iff we created it (won the claim), else null.
    const set = await this.redis.set(key, pendingValue, 'EX', ttlSeconds, 'NX');
    if (set === 'OK') return { won: true };
    // Lost the claim → read the current value (pending marker, or a cached response).
    // It can race-expire to null between the NX and the GET; treat that as still
    // pending (the caller retries) rather than fabricate a non-existent cache hit.
    const value = await this.redis.get(key);
    return { won: false, value: value ?? pendingValue };
  }

  async store(key: string, value: string, ttlSeconds: number): Promise<void> {
    await this.redis.set(key, value, 'EX', ttlSeconds);
  }

  async remove(key: string): Promise<void> {
    await this.redis.del(key);
  }
}

/**
 * Build an IdempotencyStore from REDIS_URL, or null when unset (→ disabled). Shares
 * the same lazy-connect + fail-fast settings as the rate-limit store; a connection
 * error surfaces per-command and is mapped to the service's fail-open policy.
 */
export function makeIdempotencyStoreFromEnv(): IdempotencyStore | null {
  const url = process.env.REDIS_URL;
  if (!url) return null;
  const redis = new Redis(url, {
    maxRetriesPerRequest: 1,
    commandTimeout: 1000,
    enableOfflineQueue: false,
    lazyConnect: false,
  });
  redis.on('error', () => undefined);
  return new RedisIdempotencyStore(redis);
}
