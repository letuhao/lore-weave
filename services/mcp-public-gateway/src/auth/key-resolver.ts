import { Logger } from '@nestjs/common';
import { loadConfig } from '../config/config.js';

/**
 * The resolved identity + policy a credential maps to. P0 carries only the bare
 * minimum (user + a placeholder scope set); P1 fills scopes/caps/allow_self_confirm
 * from the auth-service `mcp_api_keys` store.
 */
export interface ResolvedKey {
  userId: string;
  keyId: string;
  /** P0: `['*']` placeholder. P1: real tier∩domain scopes from the key row. */
  scopes: string[];
}

/**
 * Resolve an external-agent credential to a LoreWeave identity.
 *
 * P0 implementation: a single static test key from env (constant-time compared),
 * gated by the Q-GATE feature flag. Returns null on any failure — the caller maps
 * null to 401 (uniform, no oracle about which check failed).
 *
 * P1 replaces the body with a call to auth-service
 * `GET /internal/mcp-keys/resolve` (prefix lookup → Argon2id verify → account
 * active check), cached ~30–60s in Redis. The interface stays identical so the
 * controller does not change.
 */
export class KeyResolver {
  private readonly cfg = loadConfig();
  private readonly log = new Logger(KeyResolver.name);

  resolve(bearer: string | undefined): ResolvedKey | null {
    if (!this.cfg.featureEnabled) return null; // Q-GATE kill-switch
    if (!bearer) return null;
    // P0 static test credential — disabled unless both env values are set.
    if (!this.cfg.testKey || !this.cfg.testUserId) {
      this.log.warn('no credential store configured (P0 test key unset) — denying');
      return null;
    }
    if (!constantTimeEquals(bearer, this.cfg.testKey)) return null;
    return { userId: this.cfg.testUserId, keyId: 'p0-test-key', scopes: ['*'] };
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
