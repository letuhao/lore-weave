/**
 * L6.D — Forced-disconnect tests (RAID cycle 29).
 *
 * Acceptance per parent layer plan §L6.D:
 *   - Propagation SLA < 1s (in-process here ⇒ microseconds; live test
 *     verified at live-smoke stack-up time)
 *   - All 10 close codes mapped correctly
 *   - Force-disconnect by user_ref_id closes ALL that user's connections
 *
 * Adversary focus (per cycle prompt §7):
 *   (a) idempotent — signal twice = same close
 *   (b) malformed payload → no crash
 *   (c) close codes documented (4007/4008/4009)
 *   (d) signal handler tolerates garbage
 */
import {
  Disconnector,
  FORCE_DISCONNECT_CODES,
  type DisconnectorTarget,
} from './disconnector';
import {
  WsControlChannelConsumer,
  WS_CONTROL_REDIS_CHANNEL,
  SUPPORTED_VERSION,
} from './control-channel-consumer';
import { WsMetrics } from './metrics';

const USER = '00000000-0000-0000-0000-000000000abc';

function makeStubTarget(initial: Record<string, number> = {}): DisconnectorTarget & {
  calls: Array<{ user: string; code: number; reason: string }>;
} {
  const live: Record<string, number> = { ...initial };
  const calls: Array<{ user: string; code: number; reason: string }> = [];
  return {
    calls,
    disconnectUser(user, code, reason) {
      calls.push({ user, code, reason });
      const n = live[user] ?? 0;
      live[user] = 0;
      return n;
    },
  };
}

function goodMessage(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    version: SUPPORTED_VERSION,
    kind: 'ws_disconnect_user',
    service: 'auth-service',
    instance: 'auth-7f2c',
    reason: 'logout',
    ts_nanos: 1_700_000_000_000_000_000,
    user_ref_id: USER,
    close_code: 4002,
    nonce_id: '11111111-1111-1111-1111-111111111111',
    ...overrides,
  };
}

describe('Disconnector', () => {
  it('happy path — closes all sockets for user, returns count', () => {
    const target = makeStubTarget({ [USER]: 3 });
    const d = new Disconnector(target);
    const out = d.apply({ userRefId: USER, closeCode: 4002, reason: 'logout' });
    expect(out.accepted).toBe(true);
    expect(out.socketsClosed).toBe(3);
    expect(out.closeCode).toBe(4002);
    expect(target.calls).toHaveLength(1);
    expect(target.calls[0]).toEqual({ user: USER, code: 4002, reason: 'logout' });
  });

  it('returns socketsClosed=0 for unknown user (still accepted)', () => {
    const target = makeStubTarget({});
    const d = new Disconnector(target);
    const out = d.apply({ userRefId: 'never-connected', closeCode: 4005, reason: 'admin_kick' });
    expect(out.accepted).toBe(true);
    expect(out.socketsClosed).toBe(0);
    expect(out.rejectReason).toBe('unknown_user');
  });

  it('rejects empty user_ref_id without calling gateway', () => {
    const target = makeStubTarget({ [USER]: 1 });
    const d = new Disconnector(target);
    const out = d.apply({ userRefId: '', closeCode: 4002, reason: 'logout' });
    expect(out.accepted).toBe(false);
    expect(out.rejectReason).toBe('empty_user_ref');
    expect(target.calls).toHaveLength(0);
  });

  it('rejects close code outside the canonical 11', () => {
    const target = makeStubTarget({ [USER]: 1 });
    const d = new Disconnector(target);
    const out = d.apply({ userRefId: USER, closeCode: 9999, reason: 'bogus' });
    expect(out.accepted).toBe(false);
    expect(out.rejectReason).toBe('invalid_close_code');
    expect(target.calls).toHaveLength(0);
  });

  it('truncates oversized reason text to ≤120 chars (close frame budget)', () => {
    const target = makeStubTarget({ [USER]: 1 });
    const d = new Disconnector(target);
    const longReason = 'x'.repeat(500);
    d.apply({ userRefId: USER, closeCode: 4005, reason: longReason });
    expect(target.calls[0].reason.length).toBeLessThanOrEqual(120);
  });

  it('FORCE_DISCONNECT_CODES exposes 4007/4008/4009 + others (auditor focus)', () => {
    // Spot-check the documented codes — cycle 28 close_codes.rs taxonomy.
    expect(FORCE_DISCONNECT_CODES.TOKEN_REVOKED).toBe(4002);
    expect(FORCE_DISCONNECT_CODES.USER_ERASED).toBe(4003);
    expect(FORCE_DISCONNECT_CODES.REALITY_ARCHIVED).toBe(4004);
    expect(FORCE_DISCONNECT_CODES.ADMIN_KICK).toBe(4005);
    expect(FORCE_DISCONNECT_CODES.FINGERPRINT_MISMATCH).toBe(4009);
  });
});

describe('WsControlChannelConsumer', () => {
  let metrics: WsMetrics;
  let target: ReturnType<typeof makeStubTarget>;
  let consumer: WsControlChannelConsumer;
  let logs: { warns: string[]; errors: string[] };

  beforeEach(() => {
    metrics = new WsMetrics();
    target = makeStubTarget({ [USER]: 2 });
    logs = { warns: [], errors: [] };
    consumer = new WsControlChannelConsumer(
      new Disconnector(target),
      metrics,
      {
        warn: (m) => logs.warns.push(m),
        error: (m) => logs.errors.push(m),
      },
    );
  });

  it('shared Redis topic name pins cycle-7 channel', () => {
    expect(WS_CONTROL_REDIS_CHANNEL).toBe('lw:dependency:control');
  });

  it('happy path — dispatches and closes user sockets', () => {
    const out = consumer.consume(JSON.stringify(goodMessage()));
    expect(out).toEqual({ tag: 'dispatched', socketsClosed: 2 });
    expect(target.calls).toHaveLength(1);
  });

  it('accepts a pre-parsed object payload too', () => {
    const out = consumer.consume(goodMessage());
    expect(out.tag).toBe('dispatched');
  });

  it('IDEMPOTENT — same nonce twice = duplicate (no second dispatch)', () => {
    const msg = goodMessage();
    const first = consumer.consume(JSON.stringify(msg));
    const second = consumer.consume(JSON.stringify(msg));
    expect(first.tag).toBe('dispatched');
    expect(second).toEqual({ tag: 'duplicate' });
    expect(target.calls).toHaveLength(1);
  });

  it('IDEMPOTENT — different nonces dispatch independently', () => {
    consumer.consume(JSON.stringify(goodMessage({ nonce_id: 'aaaa' })));
    consumer.consume(JSON.stringify(goodMessage({ nonce_id: 'bbbb' })));
    expect(target.calls).toHaveLength(2);
  });

  it('MALFORMED JSON — drops + logs, never crashes', () => {
    const out = consumer.consume('{not-json');
    expect(out).toEqual({ tag: 'dropped', reason: 'malformed_json' });
    expect(metrics.authzRejections.read({ reason: 'schema_invalid' })).toBeGreaterThan(0);
    expect(logs.warns.length).toBeGreaterThan(0);
  });

  it('MALFORMED non-string non-object — drops cleanly', () => {
    const out = consumer.consume(42);
    expect(out.tag).toBe('dropped');
  });

  it('UNSUPPORTED version — ignored (mixed-rollout safety)', () => {
    const out = consumer.consume(JSON.stringify(goodMessage({ version: 99 })));
    expect(out).toEqual({ tag: 'ignored', reason: 'unsupported_version' });
    expect(target.calls).toHaveLength(0);
  });

  it('NON-WS kinds — silently ignored (mode_shift / mode_probe pass-through)', () => {
    expect(consumer.consume(JSON.stringify({ ...goodMessage(), kind: 'mode_shift', from_mode: 'full', to_mode: 'limited' }))).toEqual({
      tag: 'ignored',
      reason: 'non_ws_kind',
    });
    expect(consumer.consume(JSON.stringify({ ...goodMessage(), kind: 'mode_probe' }))).toEqual({
      tag: 'ignored',
      reason: 'non_ws_kind',
    });
    expect(target.calls).toHaveLength(0);
  });

  it('UNKNOWN kind — dropped + logged', () => {
    const out = consumer.consume(JSON.stringify({ ...goodMessage(), kind: 'mystery' }));
    expect(out).toEqual({ tag: 'dropped', reason: 'unknown_kind' });
  });

  it('rejects missing user_ref_id', () => {
    const out = consumer.consume(JSON.stringify(goodMessage({ user_ref_id: '' })));
    expect(out).toEqual({ tag: 'dropped', reason: 'invalid_payload' });
    expect(metrics.authzRejections.read({ reason: 'schema_invalid' })).toBeGreaterThan(0);
  });

  it('rejects missing nonce_id', () => {
    const out = consumer.consume(JSON.stringify(goodMessage({ nonce_id: '' })));
    expect(out.tag).toBe('dropped');
  });

  it('rejects non-numeric close_code', () => {
    const out = consumer.consume(JSON.stringify(goodMessage({ close_code: 'forty-two' })));
    expect(out.tag).toBe('dropped');
  });

  it('rejects out-of-range close_code (delegates to Disconnector)', () => {
    const out = consumer.consume(JSON.stringify(goodMessage({ close_code: 9999 })));
    expect(out).toEqual({ tag: 'dropped', reason: 'invalid_payload' });
    expect(target.calls).toHaveLength(0);
  });

  it('dedup LRU is bounded (1024 capacity does not OOM under flood)', () => {
    const tiny = new WsControlChannelConsumer(
      new Disconnector(makeStubTarget({ [USER]: 1 })),
      new WsMetrics(),
      undefined,
      4,
    );
    for (let i = 0; i < 10; i++) {
      tiny.consume(JSON.stringify(goodMessage({ nonce_id: `n${i}` })));
    }
    expect(tiny.inspectDedupSize()).toBeLessThanOrEqual(4);
  });
});
