/**
 * WS edge rate limiting (077 control #2 — clears deferral 035).
 *
 * Two basic, per-replica caps at the game-server edge:
 *   - ConnectionCap: max concurrent connections per user (close 4008).
 *   - MessageRateLimiter: per-connection fixed-window message rate (close 4006).
 *
 * Per-replica (in-process) — matches the gateway's per-replica connection cap.
 * A cross-replica/global cap (Redis token bucket) is future hardening, not V1.
 * Both classes are pure + injectable (clock passed in) → unit-testable.
 */

export interface RateLimitConfig {
  /** Max concurrent connections per user_ref_id. */
  maxConnectionsPerUser: number;
  /** Allowed messages per window, per connection. */
  messagesPerWindow: number;
  /** Fixed-window length (ms). */
  windowMs: number;
}

export const DEFAULT_RATE_LIMITS: RateLimitConfig = {
  maxConnectionsPerUser: 5,
  messagesPerWindow: 30,
  windowMs: 10_000,
};

/**
 * Per-user concurrent-connection counter. `acquire` returns false when the
 * user is already at the cap (caller rejects the handshake with close 4008).
 */
export class ConnectionCap {
  private readonly counts = new Map<string, number>();

  constructor(private readonly max: number) {}

  /** True when the user is already at the cap (check in onAuth before reserving). */
  atCap(userId: string): boolean {
    return (this.counts.get(userId) ?? 0) >= this.max;
  }

  acquire(userId: string): boolean {
    const n = this.counts.get(userId) ?? 0;
    if (n >= this.max) return false;
    this.counts.set(userId, n + 1);
    return true;
  }

  release(userId: string): void {
    const n = this.counts.get(userId) ?? 0;
    if (n <= 1) this.counts.delete(userId);
    else this.counts.set(userId, n - 1);
  }

  active(userId: string): number {
    return this.counts.get(userId) ?? 0;
  }
}

/**
 * Per-connection fixed-window message-rate limiter. `allow(now)` returns false
 * once the window count exceeds the cap (caller closes 4006). One instance per
 * connection; the clock is injected so tests are deterministic.
 */
export class MessageRateLimiter {
  private windowStart = 0;
  private count = 0;

  constructor(
    private readonly perWindow: number,
    private readonly windowMs: number,
  ) {}

  allow(nowMs: number): boolean {
    if (nowMs - this.windowStart >= this.windowMs) {
      this.windowStart = nowMs;
      this.count = 0;
    }
    this.count += 1;
    return this.count <= this.perWindow;
  }
}

/** Read rate-limit config from env (positive overrides only; else defaults). */
export function rateLimitsFromEnv(): RateLimitConfig {
  const num = (key: string, fallback: number): number => {
    const v = Number(process.env[key]);
    return Number.isFinite(v) && v > 0 ? v : fallback;
  };
  return {
    maxConnectionsPerUser: num('LW_WS_MAX_CONN_PER_USER', DEFAULT_RATE_LIMITS.maxConnectionsPerUser),
    messagesPerWindow: num('LW_WS_MSG_PER_WINDOW', DEFAULT_RATE_LIMITS.messagesPerWindow),
    windowMs: num('LW_WS_RATE_WINDOW_MS', DEFAULT_RATE_LIMITS.windowMs),
  };
}
