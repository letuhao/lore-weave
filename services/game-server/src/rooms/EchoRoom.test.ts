import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { authenticate, echoIdentity, expectedToken, EchoRoom, __setEchoEdgeForTest } from './EchoRoom.js';
import { ServerError, CloseCode } from 'colyseus';
import { CLOSE_RATE_LIMIT, CLOSE_CONNECTION_LIMIT } from '../ws/auth.js';
import type { WsAuditSink, WsAuditEvent } from '../ws/audit.js';

describe('EchoRoom.authenticate', () => {
  const TOKEN = 'test-token-xyz';

  it('returns the SERVER-decided identity when the jwt matches', () => {
    const u = authenticate({ jwt: TOKEN }, TOKEN);
    assert.equal(u.userId, echoIdentity());
  });

  // `FO-1` — the client cannot choose who it is.
  //
  // This test used to assert the OPPOSITE: `authenticate({jwt, userId:'alice'})`
  // returned `alice`. That id keys the per-user connection cap, so a client
  // could evade the cap by sending a new id per connection — the limit counted
  // whatever the caller said it was, which is not a limit.
  //
  // `userId` is now absent from `JoinOptions`, so the honest first line of
  // defence is the COMPILER: the old form of this test no longer type-checks.
  // The cast below is what an attacker has that a caller does not, and the
  // assertion is that it buys nothing.
  it('a client-supplied identity is ignored, not honoured', () => {
    const u = authenticate({ jwt: TOKEN, userId: 'alice' } as never, TOKEN);
    assert.equal(u.userId, echoIdentity());
    assert.notEqual(u.userId, 'alice');
  });

  it('the identity comes from the environment, not from a literal', () => {
    const prev = process.env.LW_ECHO_DEV_USER_ID;
    try {
      process.env.LW_ECHO_DEV_USER_ID = 'configured-dev';
      assert.equal(authenticate({ jwt: TOKEN }, TOKEN).userId, 'configured-dev');
      // Non-vacuity: with nothing configured it falls back to a fixed name, so
      // the assertion above is about the env var and not about any string.
      delete process.env.LW_ECHO_DEV_USER_ID;
      assert.equal(authenticate({ jwt: TOKEN }, TOKEN).userId, 'echo-dev');
    } finally {
      if (prev === undefined) delete process.env.LW_ECHO_DEV_USER_ID;
      else process.env.LW_ECHO_DEV_USER_ID = prev;
    }
  });

  it('throws 401 ServerError when jwt is missing', () => {
    assert.throws(
      () => authenticate({}, TOKEN),
      (err) => err instanceof ServerError && err.code === 401,
    );
  });

  it('throws 401 when options is undefined', () => {
    assert.throws(
      () => authenticate(undefined, TOKEN),
      (err) => err instanceof ServerError && err.code === 401,
    );
  });

  it('throws 401 when jwt is empty string', () => {
    assert.throws(
      () => authenticate({ jwt: '' }, TOKEN),
      (err) => err instanceof ServerError && err.code === 401,
    );
  });

  it('throws 403 ServerError when jwt does not match expected', () => {
    assert.throws(
      () => authenticate({ jwt: 'wrong-token' }, TOKEN),
      (err) => err instanceof ServerError && err.code === 403,
    );
  });
});

describe('EchoRoom.expectedToken', () => {
  it('returns env LOREWEAVE_INTERNAL_TOKEN when set', () => {
    const original = process.env.LOREWEAVE_INTERNAL_TOKEN;
    process.env.LOREWEAVE_INTERNAL_TOKEN = 'env-set-token';
    try {
      assert.equal(expectedToken(), 'env-set-token');
    } finally {
      if (original === undefined) {
        delete process.env.LOREWEAVE_INTERNAL_TOKEN;
      } else {
        process.env.LOREWEAVE_INTERNAL_TOKEN = original;
      }
    }
  });

  it('falls back to "dev_token" when env is unset', () => {
    const original = process.env.LOREWEAVE_INTERNAL_TOKEN;
    delete process.env.LOREWEAVE_INTERNAL_TOKEN;
    try {
      assert.equal(expectedToken(), 'dev_token');
    } finally {
      if (original !== undefined) {
        process.env.LOREWEAVE_INTERNAL_TOKEN = original;
      }
    }
  });
});

// D-GAME-WS-ROOM-LIFECYCLE-TEST (139): the EchoRoom edge-control WIRING
// (onAuth atCap-check, onJoin acquire+limiter+audit, onMessage rate→leave(4006),
// onLeave release/finalize/reconnect) — previously only the primitives + the
// pure auth fns were unit-tested. Drive the room methods directly on a
// prototype instance (no Colyseus transport) with the Colyseus-internal methods
// stubbed + the edge controls rebuilt per test via __setEchoEdgeForTest.
describe('EchoRoom lifecycle wiring', () => {
  class RecordingSink implements WsAuditSink {
    readonly events: WsAuditEvent[] = [];
    emit(e: WsAuditEvent): void {
      this.events.push(e);
    }
  }

  interface FakeClient {
    sessionId: string;
    auth: { userId: string };
    reconnectionToken: string;
    sent: { type: string; msg: unknown }[];
    leftCode?: number;
    send(type: string, msg: unknown): void;
    leave(code?: number): void;
  }

  function fakeClient(userId: string, sessionId: string): FakeClient {
    return {
      sessionId,
      auth: { userId },
      reconnectionToken: 'rtok-' + sessionId,
      sent: [],
      leftCode: undefined,
      send(type, msg) {
        this.sent.push({ type, msg });
      },
      leave(code) {
        this.leftCode = code;
      },
    };
  }

  // Build a driveable room WITHOUT the Colyseus transport: construct off the
  // prototype + stub the framework methods the room calls (setSeatReservationTime,
  // onMessage capture, allowReconnection).
  function makeRoom(): { room: EchoRoom; getEcho: () => (c: FakeClient, m: unknown) => void } {
    const room = Object.create(EchoRoom.prototype) as EchoRoom;
    let echoHandler: ((c: FakeClient, m: unknown) => void) | undefined;
    Object.assign(room, {
      setSeatReservationTime: () => {},
      onMessage: (type: string, h: (c: FakeClient, m: unknown) => void) => {
        if (type === 'echo') echoHandler = h;
      },
      allowReconnection: async () => {
        throw new Error('reconnection not stubbed for this test');
      },
    });
    return { room, getEcho: () => echoHandler! };
  }

  beforeEach(() => {
    // Force the static-token auth path (no shared Redis ticket store).
    delete process.env.LW_WS_REDIS_URL;
  });

  it('onJoin acquires a slot, sends welcome, audits opened', () => {
    const sink = new RecordingSink();
    const e = __setEchoEdgeForTest({ auditSink: sink });
    const { room } = makeRoom();
    const c = fakeClient('u1', 's1');
    room.onJoin(c as never);
    assert.equal(e.connectionCap.active('u1'), 1);
    assert.ok(c.sent.some((m) => m.type === 'welcome'), 'welcome sent');
    assert.ok(sink.events.some((ev) => ev.kind === 'ws.connection.opened'), 'opened audited');
  });

  it('onLeave(consented) releases the slot and audits closed', async () => {
    const sink = new RecordingSink();
    const e = __setEchoEdgeForTest({ auditSink: sink });
    const { room } = makeRoom();
    const c = fakeClient('u1', 's1');
    room.onJoin(c as never);
    await room.onLeave(c as never, CloseCode.CONSENTED);
    assert.equal(e.connectionCap.active('u1'), 0);
    const closed = sink.events.find((ev) => ev.kind === 'ws.connection.closed');
    assert.ok(closed && closed.kind === 'ws.connection.closed' && closed.reason === 'consented');
  });

  it('double onLeave releases the slot only ONCE (no double-finalize)', async () => {
    const e = __setEchoEdgeForTest();
    const { room } = makeRoom();
    const c = fakeClient('u1', 's1');
    room.onJoin(c as never);
    await room.onLeave(c as never, CloseCode.CONSENTED);
    await room.onLeave(c as never, CloseCode.CONSENTED); // second leave must be a no-op
    assert.equal(e.connectionCap.active('u1'), 0); // NOT -1
  });

  it('onAuth rejects with 4008 when the user is at the connection cap', async () => {
    const e = __setEchoEdgeForTest({ rateConfig: { maxConnectionsPerUser: 1 } });
    // The cap is keyed by the SERVER's identity now, so that is what must be
    // filled — and that is the point of `FO-1`: before, a caller sending
    // `userId: 'u2'` would have sailed past a cap filled under `u1`.
    e.connectionCap.acquire(echoIdentity());
    const { room } = makeRoom();
    const ctx = { headers: {}, ip: '1.2.3.4' } as never;
    await assert.rejects(
      () => room.onAuth({} as never, { jwt: expectedToken() }, ctx),
      (err) => err instanceof ServerError && err.code === CLOSE_CONNECTION_LIMIT,
    );
  });

  it('onMessage closes 4006 + records the reason when the rate cap is exceeded', () => {
    const e = __setEchoEdgeForTest({ rateConfig: { messagesPerWindow: 1 } });
    const { room, getEcho } = makeRoom();
    room.onCreate();
    const c = fakeClient('u1', 's1');
    room.onJoin(c as never); // creates the per-connection limiter (perWindow=1)
    const echo = getEcho();
    echo(c, 'first'); // allowed
    echo(c, 'second'); // over cap → leave(4006)
    assert.equal(c.leftCode, CLOSE_RATE_LIMIT);
    assert.equal(e.leaveReasons.get('s1'), 'rate_limit_exceeded');
  });

  it('onLeave(non-consented) finalizes when reconnection expires', async () => {
    const e = __setEchoEdgeForTest();
    const { room } = makeRoom();
    Object.assign(room, {
      allowReconnection: async () => {
        throw new Error('expired');
      },
    });
    const c = fakeClient('u1', 's1');
    room.onJoin(c as never);
    await room.onLeave(c as never, CloseCode.ABNORMAL_CLOSURE);
    assert.equal(e.connectionCap.active('u1'), 0); // released after reconnect window
  });

  it('onLeave(non-consented) KEEPS the slot when reconnection succeeds', async () => {
    const e = __setEchoEdgeForTest();
    const { room } = makeRoom();
    Object.assign(room, {
      allowReconnection: async () => undefined, // resolves → client reconnected
    });
    const c = fakeClient('u1', 's1');
    room.onJoin(c as never);
    await room.onLeave(c as never, CloseCode.ABNORMAL_CLOSURE);
    assert.equal(e.connectionCap.active('u1'), 1); // slot retained for the reconnected client
  });
});
