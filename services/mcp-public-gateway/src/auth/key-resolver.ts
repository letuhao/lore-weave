import { Logger } from '@nestjs/common';
import { loadConfig } from '../config/config.js';

/**
 * The resolved identity + policy a credential maps to. P1 fills scopes/caps/
 * allow_self_confirm from the auth-service `mcp_api_keys` store (P2/P3 consume them).
 */
export interface ResolvedKey {
  userId: string;
  keyId: string;
  scopes: string[];
  allowSelfConfirm: boolean;
  spendCapUsd: number | null;
  rateLimitRpm: number;
}

interface CacheEntry {
  value: ResolvedKey | null; // null = a cached NEGATIVE (bad key) — bounds repeat-miss cost
  expiresAt: number;
}

/**
 * Resolve an external-agent credential to a LoreWeave identity + policy.
 *
 * P1: calls auth-service `POST /internal/mcp-keys/resolve` (X-Internal-Token), which
 * does the prefix lookup + Argon2id verify + account-active check. Results are
 * cached for a short TTL (bounds revocation lag to ~TTL — see PUB / H-P) so the hot
 * path is one in-memory hit, not a DB round-trip per call. Returns null on any
 * failure — the caller maps null to a uniform 401 (no oracle).
 *
 * A dev/smoke static test key (config.testKey) short-circuits to a synthetic
 * identity WITHOUT calling auth-service, so the stack can be smoked before/without
 * a populated credential store. Empty in real deployments.
 */
// Cap the resolve cache so a flood of DISTINCT (bad) keys can't grow it without
// bound (memory DoS). Oldest entries are evicted FIFO past this size.
const RESOLVE_CACHE_MAX = 10000;

export class KeyResolver {
  private readonly cfg = loadConfig();
  private readonly log = new Logger(KeyResolver.name);
  // Keyed by the raw bearer; small TTL so a revoked/downgraded key clears quickly.
  private readonly cache = new Map<string, CacheEntry>();

  async resolve(bearer: string | undefined, now: number = Date.now()): Promise<ResolvedKey | null> {
    if (!this.cfg.featureEnabled) return null; // Q-GATE kill-switch
    if (!bearer) return null;

    // Dev/smoke static key — never calls auth-service.
    if (this.cfg.testKey && this.cfg.testUserId && constantTimeEquals(bearer, this.cfg.testKey)) {
      return {
        userId: this.cfg.testUserId,
        keyId: 'dev-test-key',
        scopes: ['*'],
        allowSelfConfirm: false,
        spendCapUsd: null,
        rateLimitRpm: 60,
      };
    }

    const cached = this.cache.get(bearer);
    if (cached && now < cached.expiresAt) return cached.value;

    const { value, cacheable } = await this.callAuthResolve(bearer);
    // Only cache a DEFINITIVE answer (a real identity, or a real 401/404 deny).
    // A transient failure (auth 429/5xx, network blip) must NOT be cached, or a
    // brief outage would deny a valid key for the whole TTL (HIGH — availability).
    if (cacheable) {
      if (this.cache.size >= RESOLVE_CACHE_MAX) {
        const oldest = this.cache.keys().next().value;
        if (oldest !== undefined) this.cache.delete(oldest);
      }
      this.cache.set(bearer, { value, expiresAt: now + this.cfg.resolveCacheTtlMs });
    }
    return value;
  }

  // callAuthResolve returns the resolved identity (or null) AND whether the answer
  // is definitive enough to cache. 200 → {identity, cacheable}. 401/404 → {null,
  // cacheable} (a real deny). 429/5xx/network → {null, NOT cacheable} (transient).
  private async callAuthResolve(bearer: string): Promise<{ value: ResolvedKey | null; cacheable: boolean }> {
    if (!this.cfg.internalToken) {
      this.log.error('cannot resolve key: INTERNAL_SERVICE_TOKEN unset');
      return { value: null, cacheable: false };
    }
    let res: Response;
    try {
      res = await fetch(`${this.cfg.authServiceUrl}/internal/mcp-keys/resolve`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-internal-token': this.cfg.internalToken },
        body: JSON.stringify({ key: bearer }),
      });
    } catch (e) {
      this.log.warn(`auth resolve failed (transient): ${e}`);
      return { value: null, cacheable: false }; // network error — don't cache
    }
    if (res.status === 401 || res.status === 404) {
      return { value: null, cacheable: true }; // definitive deny — safe to cache
    }
    if (res.status !== 200) {
      this.log.warn(`auth resolve non-OK (transient): ${res.status}`);
      return { value: null, cacheable: false }; // 429/5xx — don't cache
    }
    try {
      const body = (await res.json()) as {
        user_id?: string;
        key_id?: string;
        scopes?: string[];
        allow_self_confirm?: boolean;
        spend_cap_usd?: number | null;
        rate_limit_rpm?: number;
      };
      if (!body.user_id || !body.key_id) return { value: null, cacheable: true };
      return {
        value: {
          userId: body.user_id,
          keyId: body.key_id,
          // SECURITY: the `*` wildcard is the edge's full-bypass token, reserved for
          // the locally-minted dev static key ONLY (resolved earlier, never here). The
          // auth-service create endpoint stores `scopes` unvalidated, so a user could
          // POST scopes:["*"] directly — strip it so a STORED key can never bypass the
          // scope filter (it would otherwise defeat tier/domain least-privilege).
          scopes: (body.scopes ?? []).filter((s) => s !== '*'),
          allowSelfConfirm: body.allow_self_confirm ?? false,
          spendCapUsd: body.spend_cap_usd ?? null,
          rateLimitRpm: body.rate_limit_rpm ?? 60,
        },
        cacheable: true,
      };
    } catch (e) {
      this.log.warn(`auth resolve body parse failed: ${e}`);
      return { value: null, cacheable: false }; // malformed 200 — treat as transient
    }
  }
}

/** Length-independent constant-time string compare (avoids leaking match length). */
export function constantTimeEquals(a: string, b: string): boolean {
  const len = Math.max(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}
