/**
 * D-EDGE-RATELIMIT — ioredis → RateLimitRedis adapter.
 *
 * The ONLY place the edge rate-limiter imports the `ioredis` driver (mirrors
 * ws/redis-client.ts). The limiter itself depends on the abstract `RateLimitRedis`
 * interface only, so it stays driver-free + unit-testable without a real Redis.
 *
 * Config-gated: the client is built only when REDIS_URL is set, so dev/test runs
 * (no URL) get a null client → the middleware becomes a pass-through and never
 * requires Redis.
 *
 * Fail-open tuning (all three matter — a Redis outage must NEVER take down the edge):
 *   - `enableOfflineQueue: false` + `maxRetriesPerRequest: 1` → `eval` REJECTS fast
 *     when the connection is DOWN/refused (not queued/retried).
 *   - `commandTimeout` → `eval` REJECTS after N ms when the connection is UP but the
 *     server is WEDGED (blocked on a slow Lua, maxmemory thrash, a post-connect
 *     network black-hole, failover mid-command). Without it that command would never
 *     settle and the request would HANG forever — a fail-open hole for the most
 *     common Redis incident. On reject, the limiter's catch fails open.
 * An `'error'` listener swallows ioredis's background connection errors so they
 * can't bubble up as an unhandled exception that crashes the edge.
 */
import Redis from 'ioredis';

import type { RateLimitRedis } from './rate-limit';

/** Bound on a single Redis command on the critical path (ms). Override with
 * EDGE_RATE_LIMIT_REDIS_TIMEOUT_MS; default 100ms — well above a healthy p99 (<5ms)
 * so it only trips on a genuinely wedged server, well below any human-perceptible
 * added latency. */
const DEFAULT_REDIS_COMMAND_TIMEOUT_MS = 100;

export function makeRateLimitRedisFromEnv(
  env: NodeJS.ProcessEnv = process.env,
): RateLimitRedis | null {
  const url = env.REDIS_URL;
  if (!url) return null;
  const timeoutRaw = Number.parseInt(env.EDGE_RATE_LIMIT_REDIS_TIMEOUT_MS ?? '', 10);
  const commandTimeout =
    Number.isFinite(timeoutRaw) && timeoutRaw > 0 ? timeoutRaw : DEFAULT_REDIS_COMMAND_TIMEOUT_MS;
  const client = new Redis(url, {
    // Fail fast → fail-open fast on the critical path.
    maxRetriesPerRequest: 1,
    enableOfflineQueue: false,
    // Bound a wedged-but-connected server so eval rejects → the limiter fails open.
    commandTimeout,
  });
  // Swallow background connection errors: the limiter fails open on eval
  // rejection anyway, and an unhandled 'error' would otherwise crash the process.
  client.on('error', () => {
    /* intentionally ignored — see module doc */
  });
  return client as unknown as RateLimitRedis;
}
