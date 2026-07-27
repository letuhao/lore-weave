/**
 * CNC-Q1 — cross-replica rate limiting (audit doc 23, finding CNC-F7).
 *
 * ## The gap
 *
 * `MessageRateLimiter` and `ConnectionCap` are in-process maps, as
 * `rate-limit.ts` says outright. With N game-server replicas a client that
 * opens a connection to each gets **N x the budget**, so the IAS-D5 defence is
 * correct on one node and proportionally weaker on a fleet.
 *
 * The contrast the audit drew (CNC-D3) is the reason this file is small: the
 * turn economy needs none of this, because it lives in island state behind the
 * epoch fence and is multi-node-correct for free. Only EDGE controls have to
 * buy distributed state, and this is that purchase.
 *
 * ## Why a token bucket, and why Lua
 *
 * A token bucket allows a legitimate burst (a player chaining actions) while
 * holding the sustained rate — the shape real gameplay has. It is implemented
 * as a single Lua script because `GET` then `SET` is a race: two replicas
 * reading the same count concurrently both see room and both allow. Under
 * contention that race is not rare, it is the common case, and it fails in the
 * permissive direction. The script is the atomic unit; Redis runs it whole.
 *
 * ## Keyed by USER, not by connection
 *
 * Keying on the connection would leave the hole open — opening more
 * connections is precisely the attack. The identity comes from the
 * authenticated session (the same source that stamps `actor`, per IAS/D3).
 *
 * ## Failure behaviour: degrade, never open
 *
 * If Redis is unreachable this returns `allowed` and leaves enforcement to the
 * per-replica limiter, which is still in place. That is a deliberate choice:
 * the local limiter already bounds a single connection, so a Redis outage
 * costs the GLOBAL cap and not all limiting. Failing closed here would turn a
 * cache outage into a total play outage; failing fully open would delete the
 * per-connection cap too. It degrades to exactly what existed before this
 * file, and says so in the returned reason so it is visible rather than
 * silent.
 */

import type Redis from 'ioredis';

import { log } from '../log.js';

export interface GlobalRateLimitConfig {
  /** Bucket size — the largest legitimate burst, not the average. */
  capacity: number;
  /** Sustained refill, tokens per second. */
  refillPerSec: number;
}

/** TTL for a bucket that never refills on its own (`refillPerSec = 0`). */
const IDLE_BUCKET_TTL_SECS = 3600;

export const DEFAULT_GLOBAL_RATE_LIMIT: GlobalRateLimitConfig = {
  // Sized from the doc-22 guidance: burst = worst-case legitimate burst
  // (a player chaining actions), sustained rate well above human turn pace.
  capacity: 40,
  refillPerSec: 4,
};

export interface RateDecision {
  allowed: boolean;
  /** Tokens left after this call; -1 when the check could not run. */
  remaining: number;
  /** Set when the decision was NOT authoritative (Redis unreachable). */
  degraded?: string;
}

/**
 * Atomic token bucket.
 *
 * `now_ms` is supplied by the SERVER (this process), never by a game client —
 * a client-supplied timestamp would let a caller mint refills by claiming time
 * had passed. Redis's own clock is deliberately not read inside the script:
 * `TIME` makes a script non-deterministic and forces replication concerns,
 * and the server clock is already trusted for this purpose.
 */
const BUCKET_LUA = `
local key       = KEYS[1]
local capacity  = tonumber(ARGV[1])
local refill    = tonumber(ARGV[2])
local now_ms    = tonumber(ARGV[3])
local cost      = tonumber(ARGV[4])
local ttl_s     = tonumber(ARGV[5])

local state  = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts     = tonumber(state[2])

if tokens == nil then
  tokens = capacity
  ts = now_ms
end

-- Refill for elapsed time, clamped at capacity. max(0, ...) guards a clock
-- that went backwards (NTP step, or two replicas disagreeing): without it a
-- negative delta would SUBTRACT tokens and lock a blameless user out.
local elapsed = math.max(0, now_ms - ts) / 1000.0
tokens = math.min(capacity, tokens + elapsed * refill)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HMSET', key, 'tokens', tokens, 'ts', now_ms)
redis.call('EXPIRE', key, ttl_s)
return { allowed, math.floor(tokens) }
`;

export class GlobalRateLimiter {
  constructor(
    private readonly redis: Redis,
    private readonly cfg: GlobalRateLimitConfig = DEFAULT_GLOBAL_RATE_LIMIT,
  ) {}

  /** Bucket key. Namespaced so it cannot collide with the ticket store. */
  private key(userId: string): string {
    return `lw:ws:rl:${userId}`;
  }

  async take(userId: string, nowMs: number, cost = 1): Promise<RateDecision> {
    // Idle buckets must expire, or every user who ever connected stays
    // resident forever. Two full refills is comfortably past the point where
    // a bucket is indistinguishable from a fresh one.
    //
    // The `> 0` guard is not defensive padding — without it a `refillPerSec`
    // of 0 (a legitimate "hard budget, no refill" config, and reachable from
    // env) divides to Infinity, `String(Infinity)` reaches Redis as a
    // non-integer TTL, EXPIRE errors, and the catch below reports DEGRADED —
    // silently disabling the global cap with nothing but a log line to show
    // for it. Found by the shared-budget test, which allowed 10 of 5.
    const ttl =
      this.cfg.refillPerSec > 0
        ? Math.ceil((this.cfg.capacity / this.cfg.refillPerSec) * 2) + 1
        : IDLE_BUCKET_TTL_SECS;
    try {
      const res = (await this.redis.eval(
        BUCKET_LUA,
        1,
        this.key(userId),
        String(this.cfg.capacity),
        String(this.cfg.refillPerSec),
        String(nowMs),
        String(cost),
        String(ttl),
      )) as [number, number];
      return { allowed: res[0] === 1, remaining: res[1] };
    } catch (err) {
      // Degraded, not open: the per-replica limiter is still enforcing.
      log.warn('global-rate-limit: redis unavailable, falling back to per-replica cap', {
        err: String(err),
      });
      return { allowed: true, remaining: -1, degraded: String(err) };
    }
  }
}

/** Config from env; positive overrides only, else the defaults above. */
export function globalRateLimitFromEnv(): GlobalRateLimitConfig {
  const num = (key: string, fallback: number): number => {
    const v = Number(process.env[key]);
    return Number.isFinite(v) && v > 0 ? v : fallback;
  };
  return {
    capacity: num('LW_WS_GLOBAL_BURST', DEFAULT_GLOBAL_RATE_LIMIT.capacity),
    refillPerSec: num('LW_WS_GLOBAL_REFILL_PER_SEC', DEFAULT_GLOBAL_RATE_LIMIT.refillPerSec),
  };
}
