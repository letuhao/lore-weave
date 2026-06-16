/**
 * Thin ioredis → RedisLike adapter (077 / D-GAME-WS-EDGE-CONTROLS).
 *
 * This is the ONLY place in the gateway WS stack that imports the `ioredis`
 * driver — the RedisTicketStore + its tests depend on the abstract `RedisLike`
 * interface only, so they stay driver-free + unit-testable without a real Redis.
 *
 * Config-gated: the client is constructed only when LW_WS_REDIS_URL is set, so
 * dev/test runs (no URL) keep the in-memory store and never require Redis.
 */
import Redis from 'ioredis';

import type { RedisLike } from './redis-ticket-store';

/**
 * Build a RedisLike from LW_WS_REDIS_URL, or null when unset (→ caller falls
 * back to InMemoryTicketStore). An ioredis client structurally satisfies
 * RedisLike (it has `set(...)` + `eval(...)`).
 */
export function makeWsRedisFromEnv(): RedisLike | null {
  const url = process.env.LW_WS_REDIS_URL;
  if (!url) return null;
  return new Redis(url) as unknown as RedisLike;
}
