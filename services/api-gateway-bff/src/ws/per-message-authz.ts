/**
 * L6.C.1 — WS per-message re-authorization (RAID cycle 29).
 *
 * Per S12 §12AB.L3 the gateway MUST re-run the S2 (session_participants) and
 * S3 (privacy_level) authorization checks on EVERY inbound data message AND
 * EVERY outbound data fan-out — NOT just at handshake. Without this, a user
 * who is kicked from a session mid-connection can keep sending messages
 * until the next handshake (the S2-regression-via-WS class).
 *
 * Foundation here ships:
 *   - `SessionAuthzProvider` interface (downstream services implement)
 *   - `InMemoryAuthzProvider` (test stand-in)
 *   - `evaluateInbound` + `evaluateOutbound` pure helpers
 *   - 5-second per-(user, session) cache so the hot path doesn't hit the
 *     provider on every frame. Q-L6-1 honored — this is a NestJS extension,
 *     no sidecar.
 *
 * Per Q-L6-3 the browser WS lib is frontend-game's; this file is server-only.
 *
 * The control fast-path (ws.ping / ws.refresh / ws.close) skips authz — only
 * data envelopes are checked. Cycle 28 router (`session-router.ts`) handles
 * the kind=control fast-path before reaching us.
 */
import type { AuthzRejectionReason, WsMetrics } from './metrics';

/** Session-scoped authz inputs, materialized by upstream resolvers. */
export interface SessionAuthzContext {
  readonly userRefId: string;
  readonly allowedRealities: readonly string[];
  readonly allowedScopes: readonly string[];
}

/**
 * Resolves at runtime the per-(user, session) authorization state. The
 * gateway delegates to downstream services (roleplay/chat) over RPC so
 * the projection (session_participants, privacy_level) stays a single
 * source of truth — see L4.M ACL matrix for the s2s wiring.
 *
 * Implementations MUST be cheap (cached at provider level) and idempotent.
 */
export interface SessionAuthzProvider {
  /**
   * Returns true if `user_ref_id` is currently a participant of `session_id`.
   * Maps to S2 in S12 §12AB.L3 (session_participants table).
   */
  isParticipant(userRefId: string, sessionId: string): Promise<boolean>;

  /**
   * Returns true if `user_ref_id` may read messages at `privacyLevel` in
   * `session_id`. Maps to S3 (privacy_level enforcement). Privacy levels are
   * domain-defined (e.g., 'public', 'party', 'whisper', 'confidential').
   */
  hasPrivacyScope(userRefId: string, sessionId: string, privacyLevel: string): Promise<boolean>;
}

/** Result discriminated union — callers pattern-match. */
export type AuthzOutcome =
  | { readonly tag: 'allow' }
  | { readonly tag: 'deny'; readonly reason: AuthzRejectionReason };

/**
 * Per-message authz request input. Foundation here defines the wire shape;
 * downstream services own the payload semantics.
 *
 * `sessionId` / `privacyLevel` MAY be missing on certain message types
 * (e.g. `presence.heartbeat`); we treat absence as "session-less" and
 * fall back to scope+reality checks only (no S2/S3 hit).
 */
export interface AuthzRequest {
  readonly ctx: SessionAuthzContext;
  readonly messageType: string;
  readonly sessionId?: string;
  readonly realityId?: string;
  readonly privacyLevel?: string;
  /** Required scope for this message type — caller derives from registry. */
  readonly requiredScope?: string;
}

/**
 * In-process cache entry — single { participant, privacy_level } pair per
 * (user, session). 5-second TTL chosen so kick-out propagation < 5s
 * (matches the L6.D forced-disconnect SLA: 1s + cache miss + ACL hit).
 *
 * Cache invalidation: L6.D forced-disconnect bypasses cache (closes the
 * connection entirely) so a kicked user CAN'T fall through the cache.
 * For lighter-weight authz revocations (e.g., privacy_level downgrade)
 * the 5s window is the documented worst-case.
 */
const AUTHZ_CACHE_TTL_MS = 5_000;

interface CacheEntry {
  readonly participant: boolean;
  readonly privacyOk: boolean;
  readonly expiresAtMs: number;
}

/**
 * Per-message authz evaluator. Stateless across instances — the cache
 * lives on the instance the gateway holds (one per WsV1Gateway replica).
 */
export class PerMessageAuthz {
  private readonly cache = new Map<string, CacheEntry>();

  constructor(
    private readonly provider: SessionAuthzProvider,
    private readonly metrics: WsMetrics,
    private readonly now: () => number = () => Date.now(),
  ) {}

  /**
   * Evaluate inbound c2s data message. Outcome MUST be `allow` for the
   * router to call `data_forward` downstream.
   */
  async evaluateInbound(req: AuthzRequest): Promise<AuthzOutcome> {
    return this.evaluate(req, 'inbound');
  }

  /**
   * Evaluate outbound s2c data fan-out. Used by outbound-fanout to drop
   * frames the receiver is no longer authorized for (e.g., kicked
   * mid-broadcast).
   */
  async evaluateOutbound(req: AuthzRequest): Promise<AuthzOutcome> {
    return this.evaluate(req, 'outbound');
  }

  /** Force-evict cache entries for a user. Called by L6.D on disconnect. */
  invalidateUser(userRefId: string): void {
    for (const key of [...this.cache.keys()]) {
      if (key.startsWith(`${userRefId}`)) {
        this.cache.delete(key);
      }
    }
  }

  /** Test-only — inspect cache size. */
  /* istanbul ignore next — instrumentation only */
  inspectCacheSize(): number {
    return this.cache.size;
  }

  private async evaluate(
    req: AuthzRequest,
    _direction: 'inbound' | 'outbound',
  ): Promise<AuthzOutcome> {
    // 1. Scope check — derived from the ticket, never expires within a
    // connection. No provider hit needed.
    if (req.requiredScope && !req.ctx.allowedScopes.includes(req.requiredScope)) {
      this.metrics.onAuthzReject('scope_not_allowed');
      return { tag: 'deny', reason: 'scope_not_allowed' };
    }

    // 2. Reality binding — derived from the ticket. No provider hit.
    if (req.realityId && !req.ctx.allowedRealities.includes(req.realityId)) {
      this.metrics.onAuthzReject('reality_not_allowed');
      return { tag: 'deny', reason: 'reality_not_allowed' };
    }

    // 3. If no session is in scope (e.g., presence heartbeats), short
    // circuit — scope+reality were enough.
    if (!req.sessionId) {
      return { tag: 'allow' };
    }

    // 4. S2 + S3 — cached.
    const cacheKey = `${req.ctx.userRefId}${req.sessionId}${req.privacyLevel ?? ''}`;
    const nowMs = this.now();
    let entry = this.cache.get(cacheKey);
    if (!entry || entry.expiresAtMs <= nowMs) {
      const participant = await this.provider.isParticipant(req.ctx.userRefId, req.sessionId);
      const privacyOk = req.privacyLevel
        ? await this.provider.hasPrivacyScope(req.ctx.userRefId, req.sessionId, req.privacyLevel)
        : true;
      entry = { participant, privacyOk, expiresAtMs: nowMs + AUTHZ_CACHE_TTL_MS };
      this.cache.set(cacheKey, entry);
    }

    if (!entry.participant) {
      this.metrics.onAuthzReject('s2_not_in_session');
      return { tag: 'deny', reason: 's2_not_in_session' };
    }
    if (!entry.privacyOk) {
      this.metrics.onAuthzReject('s3_privacy_violation');
      return { tag: 'deny', reason: 's3_privacy_violation' };
    }
    return { tag: 'allow' };
  }
}

/**
 * Trivial in-memory provider for tests + bootstrapping. Production wires
 * a roleplay-service RPC client implementing the same interface.
 */
export class InMemoryAuthzProvider implements SessionAuthzProvider {
  private readonly participants = new Set<string>();
  private readonly privacyGrants = new Set<string>();

  addParticipant(userRefId: string, sessionId: string): void {
    this.participants.add(`${userRefId}${sessionId}`);
  }

  removeParticipant(userRefId: string, sessionId: string): void {
    this.participants.delete(`${userRefId}${sessionId}`);
  }

  grantPrivacy(userRefId: string, sessionId: string, privacyLevel: string): void {
    this.privacyGrants.add(`${userRefId}${sessionId}${privacyLevel}`);
  }

  revokePrivacy(userRefId: string, sessionId: string, privacyLevel: string): void {
    this.privacyGrants.delete(`${userRefId}${sessionId}${privacyLevel}`);
  }

  async isParticipant(userRefId: string, sessionId: string): Promise<boolean> {
    return this.participants.has(`${userRefId}${sessionId}`);
  }

  async hasPrivacyScope(userRefId: string, sessionId: string, privacyLevel: string): Promise<boolean> {
    return this.privacyGrants.has(`${userRefId}${sessionId}${privacyLevel}`);
  }
}

export const PER_MESSAGE_AUTHZ_CACHE_TTL_MS = AUTHZ_CACHE_TTL_MS;
