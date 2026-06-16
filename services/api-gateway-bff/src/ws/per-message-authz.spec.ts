/**
 * L6.C — per-message authz tests (RAID cycle 29).
 *
 * Acceptance per parent layer plan:
 *   - Per-message re-auth verifiable in test
 *   - Rejection latency < 1ms (in-process cached path)
 *   - S2 + S3 regressions caught
 */
import {
  InMemoryAuthzProvider,
  PerMessageAuthz,
  PER_MESSAGE_AUTHZ_CACHE_TTL_MS,
  type AuthzRequest,
  type SessionAuthzContext,
} from './per-message-authz';
import { WsMetrics } from './metrics';

const USER = '00000000-0000-0000-0000-000000000abc';
const SESSION = '11111111-1111-1111-1111-111111111111';
const REALITY = '22222222-2222-2222-2222-222222222222';

function ctxOf(overrides: Partial<SessionAuthzContext> = {}): SessionAuthzContext {
  return {
    userRefId: USER,
    allowedRealities: [REALITY],
    allowedScopes: ['chat'],
    ...overrides,
  };
}

function reqOf(overrides: Partial<AuthzRequest> = {}): AuthzRequest {
  return {
    ctx: ctxOf(),
    messageType: 'chat.message',
    sessionId: SESSION,
    realityId: REALITY,
    privacyLevel: 'public',
    requiredScope: 'chat',
    ...overrides,
  };
}

describe('PerMessageAuthz', () => {
  let metrics: WsMetrics;
  let provider: InMemoryAuthzProvider;
  let now: number;
  let authz: PerMessageAuthz;

  beforeEach(() => {
    metrics = new WsMetrics();
    provider = new InMemoryAuthzProvider();
    now = 1_000_000;
    authz = new PerMessageAuthz(provider, metrics, () => now);
  });

  describe('scope/reality fast-path (no provider hit needed)', () => {
    it('happy path — scope+reality+session+privacy all ok', async () => {
      provider.addParticipant(USER, SESSION);
      provider.grantPrivacy(USER, SESSION, 'public');
      const out = await authz.evaluateInbound(reqOf());
      expect(out).toEqual({ tag: 'allow' });
      expect(metrics.authzRejections.snapshot()).toHaveLength(0);
    });

    it('rejects scope not in ticket → scope_not_allowed', async () => {
      const out = await authz.evaluateInbound(reqOf({ requiredScope: 'admin' }));
      expect(out).toEqual({ tag: 'deny', reason: 'scope_not_allowed' });
      expect(metrics.authzRejections.read({ reason: 'scope_not_allowed' })).toBe(1);
    });

    it('rejects reality not in ticket → reality_not_allowed', async () => {
      const out = await authz.evaluateInbound(
        reqOf({ realityId: '99999999-9999-9999-9999-999999999999' }),
      );
      expect(out).toEqual({ tag: 'deny', reason: 'reality_not_allowed' });
      expect(metrics.authzRejections.read({ reason: 'reality_not_allowed' })).toBe(1);
    });

    it('skips S2/S3 lookup when sessionId absent (presence heartbeat case)', async () => {
      const spy = jest.spyOn(provider, 'isParticipant');
      const out = await authz.evaluateInbound(
        reqOf({ sessionId: undefined, privacyLevel: undefined }),
      );
      expect(out).toEqual({ tag: 'allow' });
      expect(spy).not.toHaveBeenCalled();
    });
  });

  describe('S2 — session_participants (S2-regression-via-WS class)', () => {
    it('user not in session → s2_not_in_session', async () => {
      // intentionally do NOT add participant
      provider.grantPrivacy(USER, SESSION, 'public');
      const out = await authz.evaluateInbound(reqOf());
      expect(out).toEqual({ tag: 'deny', reason: 's2_not_in_session' });
      expect(metrics.authzRejections.read({ reason: 's2_not_in_session' })).toBe(1);
    });

    it('S2 REGRESSION — user kicked mid-connection rejected within cache-TTL', async () => {
      provider.addParticipant(USER, SESSION);
      provider.grantPrivacy(USER, SESSION, 'public');
      // First message — allowed (cache populated).
      expect((await authz.evaluateInbound(reqOf())).tag).toBe('allow');
      // User kicked.
      provider.removeParticipant(USER, SESSION);
      // Within cache TTL → still allowed (documented limit).
      now += 1_000;
      expect((await authz.evaluateInbound(reqOf())).tag).toBe('allow');
      // After TTL → rejected on re-check.
      now += PER_MESSAGE_AUTHZ_CACHE_TTL_MS + 1;
      const out = await authz.evaluateInbound(reqOf());
      expect(out).toEqual({ tag: 'deny', reason: 's2_not_in_session' });
    });
  });

  describe('S3 — privacy_level enforcement', () => {
    it('participant but no privacy grant → s3_privacy_violation', async () => {
      provider.addParticipant(USER, SESSION);
      // No privacy grant.
      const out = await authz.evaluateInbound(reqOf({ privacyLevel: 'confidential' }));
      expect(out).toEqual({ tag: 'deny', reason: 's3_privacy_violation' });
      expect(metrics.authzRejections.read({ reason: 's3_privacy_violation' })).toBe(1);
    });

    it('outbound fan-out drops frame when receiver privacy downgraded', async () => {
      provider.addParticipant(USER, SESSION);
      provider.grantPrivacy(USER, SESSION, 'confidential');
      expect((await authz.evaluateOutbound(reqOf({ privacyLevel: 'confidential' }))).tag).toBe('allow');
      // Receiver loses confidential clearance.
      provider.revokePrivacy(USER, SESSION, 'confidential');
      now += PER_MESSAGE_AUTHZ_CACHE_TTL_MS + 1;
      const out = await authz.evaluateOutbound(reqOf({ privacyLevel: 'confidential' }));
      expect(out).toEqual({ tag: 'deny', reason: 's3_privacy_violation' });
    });
  });

  describe('cache discipline', () => {
    it('5s TTL — second call within TTL hits cache (no extra provider call)', async () => {
      provider.addParticipant(USER, SESSION);
      provider.grantPrivacy(USER, SESSION, 'public');
      const spy = jest.spyOn(provider, 'isParticipant');
      await authz.evaluateInbound(reqOf());
      await authz.evaluateInbound(reqOf());
      await authz.evaluateInbound(reqOf());
      expect(spy).toHaveBeenCalledTimes(1);
    });

    it('cache expires exactly at TTL boundary', async () => {
      provider.addParticipant(USER, SESSION);
      provider.grantPrivacy(USER, SESSION, 'public');
      const spy = jest.spyOn(provider, 'isParticipant');
      await authz.evaluateInbound(reqOf());
      now += PER_MESSAGE_AUTHZ_CACHE_TTL_MS + 1;
      await authz.evaluateInbound(reqOf());
      expect(spy).toHaveBeenCalledTimes(2);
    });

    it('invalidateUser drops all entries for that user (L6.D wiring)', async () => {
      provider.addParticipant(USER, SESSION);
      provider.grantPrivacy(USER, SESSION, 'public');
      await authz.evaluateInbound(reqOf());
      expect(authz.inspectCacheSize()).toBe(1);
      authz.invalidateUser(USER);
      expect(authz.inspectCacheSize()).toBe(0);
    });
  });

  describe('latency budget (hot-path)', () => {
    it('cached evaluate <1ms', async () => {
      provider.addParticipant(USER, SESSION);
      provider.grantPrivacy(USER, SESSION, 'public');
      // Warm the cache.
      await authz.evaluateInbound(reqOf());
      const start = process.hrtime.bigint();
      for (let i = 0; i < 1000; i++) {
        await authz.evaluateInbound(reqOf());
      }
      const elapsedNs = Number(process.hrtime.bigint() - start);
      const perCallMs = elapsedNs / 1_000_000 / 1000;
      // Pessimistic ceiling — 1ms target is the spec; even 0.5ms is fine here.
      expect(perCallMs).toBeLessThan(1);
    });
  });
});
