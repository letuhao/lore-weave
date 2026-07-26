import { Logger } from '@nestjs/common';

/**
 * Per-key rate limiting at the public edge (PUB-8). A leaked or abusive key is
 * bounded to its `rate_limit_rpm` (resolved from the auth-service credential
 * store) via a fixed 60s window counter in Redis, shared across edge replicas.
 *
 * Fail policy (PUB-8) — when the store is UNAVAILABLE we cannot count, so:
 *   - READS fail OPEN (allow) — availability: a Redis blip must not take down the
 *     read surface.
 *   - WRITES fail CLOSED (deny) — safety: an unbounded write flood during an
 *     outage is the abuse we're guarding against.
 * When no store is configured at all (REDIS_URL unset — dev), rate limiting is
 * DISABLED (everything allowed) and logged once, never silently half-on.
 */

/** The minimal Redis surface the limiter needs — keeps it driver-free + testable. */
export interface RateLimitStore {
  /**
   * Atomically increment the counter at `key` BY `by` and return the NEW value;
   * sets the TTL to `ttlSeconds` on first creation so the window self-expires.
   * Throws on a backend error (the limiter maps that to the fail-open/closed policy).
   */
  incrByWithTtl(key: string, by: number, ttlSeconds: number): Promise<number>;
}

export interface RateLimitResult {
  allowed: boolean;
  /** seconds until the window resets — sent as Retry-After on a 429. */
  retryAfter: number;
  limit: number;
  /** remaining calls in the current window (0 when blocked). */
  remaining: number;
}

const WINDOW_SECONDS = 60;

export class RateLimiter {
  private readonly log = new Logger(RateLimiter.name);
  private warnedNoStore = false;

  // `store` is null when REDIS_URL is unset → rate limiting disabled (fail-open).
  constructor(private readonly store: RateLimitStore | null) {}

  /**
   * Check whether a call from `keyId` (limited to `rpm`/min) may proceed.
   * `isWrite` selects the fail policy when the store errors (PUB-8). `weight` is the
   * number of billable units the request represents — 1 for a single call, but the
   * count of `tools/call` entries for a JSON-RPC BATCH, so a batch can't smuggle N
   * executions past a per-request counter (the limit bounds WORK, not HTTP requests).
   */
  async check(
    keyId: string,
    rpm: number,
    isWrite: boolean,
    weight: number = 1,
    now: number = Date.now(),
  ): Promise<RateLimitResult> {
    const limit = rpm > 0 ? rpm : 1; // a 0/negative rpm would block everything; floor at 1
    const by = weight > 0 ? Math.floor(weight) : 1;
    const windowStart = Math.floor(now / 1000 / WINDOW_SECONDS);
    const retryAfter = WINDOW_SECONDS - Math.floor((now / 1000) % WINDOW_SECONDS);

    if (!this.store) {
      if (!this.warnedNoStore) {
        this.log.warn('rate limiting DISABLED (no REDIS_URL) — all calls allowed; set REDIS_URL in any real deployment');
        this.warnedNoStore = true;
      }
      return { allowed: true, retryAfter, limit, remaining: limit };
    }

    const redisKey = `mcp:rl:${keyId}:${windowStart}`;
    let count: number;
    try {
      count = await this.store.incrByWithTtl(redisKey, by, WINDOW_SECONDS);
    } catch (e) {
      // Store outage → PUB-8 fail policy: reads open, writes closed.
      this.log.warn(`rate-limit store error (failing ${isWrite ? 'CLOSED' : 'OPEN'}): ${e}`);
      return { allowed: !isWrite, retryAfter, limit, remaining: 0 };
    }
    const allowed = count <= limit;
    return { allowed, retryAfter, limit, remaining: Math.max(0, limit - count) };
  }
}
