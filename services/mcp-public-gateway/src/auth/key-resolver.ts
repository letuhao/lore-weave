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

    const resolved = await this.callAuthResolve(bearer);
    this.cache.set(bearer, { value: resolved, expiresAt: now + this.cfg.resolveCacheTtlMs });
    return resolved;
  }

  private async callAuthResolve(bearer: string): Promise<ResolvedKey | null> {
    if (!this.cfg.internalToken) {
      this.log.error('cannot resolve key: INTERNAL_SERVICE_TOKEN unset');
      return null;
    }
    try {
      const res = await fetch(`${this.cfg.authServiceUrl}/internal/mcp-keys/resolve`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-internal-token': this.cfg.internalToken },
        body: JSON.stringify({ key: bearer }),
      });
      if (res.status !== 200) return null; // 401/404/429 → unresolved (uniform deny upstream)
      const body = (await res.json()) as {
        user_id?: string;
        key_id?: string;
        scopes?: string[];
        allow_self_confirm?: boolean;
        spend_cap_usd?: number | null;
        rate_limit_rpm?: number;
      };
      if (!body.user_id || !body.key_id) return null;
      return {
        userId: body.user_id,
        keyId: body.key_id,
        scopes: body.scopes ?? [],
        allowSelfConfirm: body.allow_self_confirm ?? false,
        spendCapUsd: body.spend_cap_usd ?? null,
        rateLimitRpm: body.rate_limit_rpm ?? 60,
      };
    } catch (e) {
      this.log.warn(`auth resolve failed: ${e}`);
      return null;
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
