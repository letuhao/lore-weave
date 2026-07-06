/**
 * D-EDGE-RATELIMIT — HTTP-edge fixed-window rate limiter for api-gateway-bff.
 *
 * This is a CRITICAL-PATH middleware: it runs on EVERY proxied HTTP request, so
 * three properties are non-negotiable:
 *   1. **Fail-OPEN.** ANY Redis error (timeout, connection refused, script error,
 *      malformed reply, or a WEDGED server that never replies — bounded by the
 *      client's `commandTimeout`) LOGS a warning and ALLOWS the request. A Redis
 *      outage must NEVER take down the edge.
 *   2. **Cheap + atomic.** One Lua step per key (INCR + first-hit/self-heal PEXPIRE
 *      + PTTL) in a single server-side round-trip.
 *   3. **The client CANNOT control the key or the exemption.** Every earlier version
 *      of this leaked bypasses by trusting client-supplied signals (a mere
 *      `x-internal-token` header, an `Accept: text/event-stream` header, a
 *      `/stream`-suffixed path, a forged JWT `sub`, a spoofed `X-Forwarded-For`).
 *      Here: the internal-token exemption is a constant-time VALUE match against the
 *      configured secret (a non-matching header is STRIPPED so it can't spoof
 *      internal trust upstream); the client IP comes from Express `trust proxy`
 *      (NOT the raw leftmost XFF hop); and every request is bounded by its IP key
 *      even when it also carries a (spoofable) user `sub` — so a rotating-sub
 *      attacker is still capped by IP.
 *
 * Note on streaming: a fixed-window counter INCRs ONCE per HTTP request. An SSE
 * stream is a single long-lived request → a single INCR (the open stream never
 * re-enters the middleware), so streaming routes need NO exemption — which is why
 * the old, spoofable Accept/`/stream` exemptions were removed.
 */
import type { Request, Response, NextFunction } from 'express';
import * as crypto from 'crypto';
import * as jwt from 'jsonwebtoken';

/**
 * Minimal Redis surface — structurally satisfied by an ioredis client.
 * `eval(script, numkeys, key, ...argv)` → reply `{ count, pttlMs }`.
 */
export interface RateLimitRedis {
  eval(script: string, numkeys: number, key: string, ...argv: (number | string)[]): Promise<unknown>;
}

/**
 * Atomic fixed-window step. INCR; set the window TTL on the first hit; ALSO
 * self-heal a key that somehow lost its TTL (PTTL < 0 while the key exists) so a
 * counter can never get permanently stuck without an expiry and lock a key out
 * forever (L1). Read the remaining TTL for an accurate Retry-After. Single
 * round-trip. KEYS[1]=key, ARGV[1]=windowMs.
 */
export const RATE_LIMIT_LUA =
  "local c = redis.call('INCR', KEYS[1]); " +
  "local ttl = redis.call('PTTL', KEYS[1]); " +
  "if c == 1 or ttl < 0 then redis.call('PEXPIRE', KEYS[1], ARGV[1]); ttl = tonumber(ARGV[1]) end; " +
  'return { c, ttl }';

export interface RateLimitConfig {
  /** When false, the middleware is a pass-through (EDGE_RATE_LIMIT_ENABLED=false). */
  readonly enabled: boolean;
  /** Max requests per USER key (sub) per window (EDGE_RATE_LIMIT_MAX). */
  readonly userMax: number;
  /** Max requests per IP key per window — the backstop a forged/rotating sub cannot
   * escape (EDGE_RATE_LIMIT_IP_MAX). Higher than userMax to tolerate shared NAT. */
  readonly ipMax: number;
  /** Window length in milliseconds (EDGE_RATE_LIMIT_WINDOW_S × 1000). */
  readonly windowMs: number;
  /** The internal service token: a request whose `x-internal-token` VALUE equals
   * this is exempt (service-to-service). Empty ⇒ no request is ever internal-exempt
   * AND every inbound x-internal-token is stripped (it can only be a spoof). */
  readonly internalToken: string;
}

export const DEFAULT_EDGE_RATE_LIMIT_MAX = 300;
export const DEFAULT_EDGE_RATE_LIMIT_IP_MAX = 1500;
export const DEFAULT_EDGE_RATE_LIMIT_WINDOW_S = 60;

function parsePositiveInt(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

/**
 * Load config from env with secure defaults. `enabled` is true unless explicitly
 * "false" (a missing/garbled value keeps the limiter ON).
 */
export function loadRateLimitConfig(env: NodeJS.ProcessEnv = process.env): RateLimitConfig {
  const enabled = (env.EDGE_RATE_LIMIT_ENABLED ?? 'true').toLowerCase() !== 'false';
  const userMax = parsePositiveInt(env.EDGE_RATE_LIMIT_MAX, DEFAULT_EDGE_RATE_LIMIT_MAX);
  const ipMax = parsePositiveInt(env.EDGE_RATE_LIMIT_IP_MAX, DEFAULT_EDGE_RATE_LIMIT_IP_MAX);
  const windowS = parsePositiveInt(env.EDGE_RATE_LIMIT_WINDOW_S, DEFAULT_EDGE_RATE_LIMIT_WINDOW_S);
  return Object.freeze({
    enabled,
    userMax,
    ipMax,
    windowMs: windowS * 1000,
    internalToken: env.INTERNAL_SERVICE_TOKEN ?? '',
  });
}

export interface RateLimitRequest {
  readonly path: string;
  readonly headers: Record<string, string | string[] | undefined>;
  /** Express-computed client IP (correct only with `trust proxy` set). */
  readonly ip?: string;
  readonly socket?: { remoteAddress?: string };
}

function headerValue(v: string | string[] | undefined): string | undefined {
  if (Array.isArray(v)) return v[0];
  return v;
}

/** Constant-time string equality (length-guarded). */
function timingSafeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}

/**
 * A request is internal-service traffic iff its `x-internal-token` VALUE equals the
 * configured secret (constant-time). NEVER exempt on mere presence — a client can
 * send any header value. Empty configured token ⇒ never internal.
 */
export function isInternalToken(req: RateLimitRequest, config: RateLimitConfig): boolean {
  if (!config.internalToken) return false;
  const v = headerValue(req.headers['x-internal-token']);
  return typeof v === 'string' && timingSafeEqual(v, config.internalToken);
}

/**
 * True when a request must NEVER be rate-limited: liveness/readiness probes, or a
 * VALUE-verified internal-service call. (No client-controlled exemption — see the
 * module doc on why the Accept/streaming exemptions were removed.)
 */
export function isRateLimitExempt(req: RateLimitRequest, config: RateLimitConfig): boolean {
  if (req.path === '/health' || req.path === '/health/ready') return true;
  return isInternalToken(req, config);
}

/**
 * Client IP for the IP-bucket key. Reads `req.ip`, which Express derives from the
 * trusted-proxy chain when `trust proxy` is configured (main/gateway-setup) — so an
 * attacker cannot rotate the key by spoofing a leftmost `X-Forwarded-For` hop.
 * Falls back to the socket address.
 */
export function clientIp(req: RateLimitRequest): string {
  return req.ip || req.socket?.remoteAddress || 'unknown';
}

/**
 * DECODE (do NOT verify) a Bearer token → its `sub`. This is only a bucket key; a
 * forged token merely buckets itself (and is still bounded by the IP key). Null
 * when there's no usable sub.
 */
function subFromBearer(authorization: string | undefined): string | null {
  if (!authorization || !/^Bearer\s+/i.test(authorization)) return null;
  const token = authorization.replace(/^Bearer\s+/i, '').trim();
  if (!token) return null;
  try {
    const decoded = jwt.decode(token);
    if (decoded && typeof decoded === 'object' && typeof decoded.sub === 'string' && decoded.sub) {
      return decoded.sub;
    }
  } catch {
    /* malformed → no user key, IP key still applies */
  }
  return null;
}

/** The per-user bucket key, or null when the request carries no usable sub. */
export function userKeyFor(req: RateLimitRequest): string | null {
  const sub = subFromBearer(headerValue(req.headers['authorization']));
  return sub ? `rl:u:${sub}` : null;
}

/** The per-IP bucket key — ALWAYS present, the backstop for a forged/rotating sub. */
export function ipKeyFor(req: RateLimitRequest): string {
  return `rl:ip:${clientIp(req)}`;
}

export interface RateLimitDecision {
  readonly allowed: boolean;
  readonly count?: number;
  readonly retryAfterS?: number;
  /** Allowed because of a Redis error (fail-open), not because under limit. */
  readonly failedOpen?: boolean;
}

/**
 * One atomic fixed-window step for a single key against `max`. FAIL-OPEN on any
 * error → `{ allowed: true, failedOpen: true }`.
 */
export async function checkRateLimit(
  redis: RateLimitRedis,
  key: string,
  max: number,
  windowMs: number,
): Promise<RateLimitDecision> {
  try {
    const raw = await redis.eval(RATE_LIMIT_LUA, 1, key, windowMs);
    const arr = Array.isArray(raw) ? (raw as unknown[]) : [raw];
    const count = Number(arr[0]);
    if (!Number.isFinite(count)) return { allowed: true, failedOpen: true };
    const ttlMs = Number(arr[1]);
    const windowS = Math.ceil(windowMs / 1000);
    const retryAfterS =
      Number.isFinite(ttlMs) && ttlMs > 0 ? Math.max(1, Math.ceil(ttlMs / 1000)) : windowS;
    if (count > max) return { allowed: false, count, retryAfterS };
    return { allowed: true, count };
  } catch {
    return { allowed: true, failedOpen: true };
  }
}

export interface RateLimitedBody {
  error: 'rate_limited';
  retry_after: number;
}

export interface RateLimitLogger {
  warn(message: string): void;
}

const FAIL_OPEN_LOG_INTERVAL_MS = 10_000;

/**
 * Build the Express middleware. Pass-through when `redis` is null or disabled.
 * Otherwise: exempt health + value-verified internal traffic (keeping the header);
 * STRIP a non-matching x-internal-token so a spoof can't ride upstream; then bound
 * the request by BOTH its IP key (always) and its user key (if a sub is present) —
 * 429 if EITHER trips. The whole path fails OPEN on any error.
 */
export function makeRateLimitMiddleware(
  redis: RateLimitRedis | null,
  config: RateLimitConfig,
  logger?: RateLimitLogger,
): (req: Request, res: Response, next: NextFunction) => void {
  let lastFailOpenLogAt = 0;
  const noop = !redis || !config.enabled;

  const maybeLogFailOpen = (): void => {
    if (!logger) return;
    const now = Date.now();
    if (now - lastFailOpenLogAt >= FAIL_OPEN_LOG_INTERVAL_MS) {
      lastFailOpenLogAt = now;
      logger.warn('edge rate-limit: Redis unavailable/slow — failing OPEN (allowing traffic)');
    }
  };

  return (req: Request, res: Response, next: NextFunction): void => {
    if (noop) return next();
    let ipKey: string;
    let userKey: string | null;
    try {
      if (isRateLimitExempt(req, config)) return next();
      // A present-but-non-matching internal token is a spoof — strip it so
      // createProxyMiddleware does not forward it as fake internal trust.
      if (req.headers['x-internal-token'] !== undefined) delete req.headers['x-internal-token'];
      ipKey = ipKeyFor(req);
      userKey = userKeyFor(req);
    } catch {
      return next(); // fail open on any sync failure
    }

    const checks: Promise<RateLimitDecision>[] = [
      checkRateLimit(redis as RateLimitRedis, ipKey, config.ipMax, config.windowMs),
    ];
    if (userKey) {
      checks.push(checkRateLimit(redis as RateLimitRedis, userKey, config.userMax, config.windowMs));
    }

    Promise.all(checks)
      .then((decisions) => {
        if (decisions.some((d) => d.failedOpen)) maybeLogFailOpen();
        const denied = decisions.filter((d) => !d.allowed);
        if (denied.length === 0) return next();
        const retryAfter =
          Math.max(...denied.map((d) => d.retryAfterS ?? Math.ceil(config.windowMs / 1000)));
        const body: RateLimitedBody = { error: 'rate_limited', retry_after: retryAfter };
        res
          .status(429)
          .set('Retry-After', String(retryAfter))
          .set('Content-Type', 'application/json')
          .end(JSON.stringify(body));
      })
      .catch(() => {
        // checkRateLimit already fails open; never let a rejection block the request.
        next();
      });
  };
}
