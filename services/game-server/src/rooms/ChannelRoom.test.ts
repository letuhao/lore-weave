import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ChannelRoom, streamFor, proposalStreamFor, parseEnvelope } from './ChannelRoom.js';

// Security regressions for the two holes found while wiring the browser
// (2026-07-27). Both were live in the PoC and both are silent: nothing errors,
// the wrong thing just works.

test('onAuth FAILS CLOSED when no ticket store and no dev opt-in', async () => {
  // Kill-mutation: fall back to the static token whenever the redeemer is
  // absent — a production deploy that forgets Redis would then accept anyone.
  const prevRedis = process.env.LW_WS_REDIS_URL;
  const prevDev = process.env.LW_WS_DEV_ALLOW_STATIC;
  delete process.env.LW_WS_REDIS_URL;
  delete process.env.LW_WS_DEV_ALLOW_STATIC;
  const room = new ChannelRoom();
  await assert.rejects(
    () => room.onAuth({} as never, { jwt: 'dev_token' }, { headers: new Map(), ip: '1.2.3.4' } as never),
    /fail closed/,
  );
  if (prevRedis) process.env.LW_WS_REDIS_URL = prevRedis;
  if (prevDev) process.env.LW_WS_DEV_ALLOW_STATIC = prevDev;
});

test('onAuth rejects a wrong dev token even with the opt-in set', async () => {
  process.env.LW_WS_DEV_ALLOW_STATIC = '1';
  process.env.LOREWEAVE_INTERNAL_TOKEN = 'right';
  const room = new ChannelRoom();
  await assert.rejects(
    () => room.onAuth({} as never, { jwt: 'wrong' }, { headers: new Map(), ip: '1.2.3.4' } as never),
    /invalid token/,
  );
  const ok = await room.onAuth({} as never, { jwt: 'right' }, { headers: new Map(), ip: '1.2.3.4' } as never);
  assert.ok(ok.userId, 'a valid dev token yields a userId');
  delete process.env.LW_WS_DEV_ALLOW_STATIC;
});

test('stream keys are derived, never client-supplied', () => {
  // The room computes both keys from ids; a caller cannot hand it a stream.
  assert.equal(streamFor('r1'), 'lw.events.r1');
  assert.equal(proposalStreamFor('r1', '2'), 'reality:r1:cell:2:proposals');
});

test('parseEnvelope refuses an envelope with no event_type', () => {
  assert.throws(() => parseEnvelope(['reality_id', 'x']), /no event_type/);
});

// IAS-D5 / IAS-A6 — the spam gate. Until this landed, ChannelRoom had NO rate
// limiter (the limiter was wired only into EchoRoom, the V0 demo), so the room
// carrying the game was the unprotected one.
test('turn.submit over the cap closes the socket and reaches NEITHER the bus nor an event', async () => {
  process.env.LW_WS_MSG_PER_WINDOW = '3';
  process.env.LW_WS_RATE_WINDOW_MS = '60000';

  const room = new ChannelRoom();
  // Minimal wiring: a redis stand-in that RECORDS instead of writing, so the
  // assertion is about what crossed the boundary, not about what was logged.
  const xadds: unknown[][] = [];
  (room as unknown as { redis: unknown }).redis = {
    xadd: async (...args: unknown[]) => {
      xadds.push(args);
      return '1-1';
    },
  };
  (room as unknown as { opts: unknown }).opts = { realityId: 'r1', channelId: '1' };
  (room as unknown as { view: unknown }).view = { actors: {}, turn_number: '0', last_event_id: '0' };

  const sent: string[] = [];
  let leftWith: number | undefined;
  const client = {
    sessionId: 's1',
    send: (type: string) => sent.push(type),
    leave: (code: number) => {
      leftWith = code;
    },
  };
  // Both maps, because `onJoin` sets both: `userOf` UNCONDITIONALLY and
  // `actorOf` only when a binding exists. Setting the actor alone builds a
  // session with an actor and no user — a state production cannot reach,
  // and one that `SEALED-SUBJECT` now refuses, because a proposal carries
  // the USER. The fixture reached past `onJoin` into the privates, which is
  // why it could construct it at all.
  (room as unknown as { actorOf: Map<string, string> }).actorOf.set('s1', '1');
  (room as unknown as { userOf: Map<string, string> }).userOf.set('s1', 'u-1');
  (room as unknown as { submitLimiters: Map<string, unknown> }).submitLimiters.set(
    's1',
    new (await import('../ws/rate-limit.js')).MessageRateLimiter(3, 60000),
  );

  const submit = (room as unknown as {
    submit: (c: unknown, m: unknown) => Promise<void>;
  }).submit.bind(room);

  for (let i = 0; i < 10; i++) {
    await submit(client, { client_request_id: `req-${i}`, action: { tool: 'strike' } });
  }

  assert.equal(leftWith, 4006, 'over the cap the connection is closed');
  assert.equal(xadds.length, 3, 'only the first 3 reached the bus — the other 7 emitted nothing');
  // Kill-mutation: answering the refusal with client.send('turn.error') would
  // look friendlier and cost nothing here, but at scale a durable refusal is
  // exactly the write-amplification IAS-A6 forbids. Refused traffic must be
  // counted, not narrated.
  assert.ok(
    !sent.includes('turn.error'),
    'a transport refusal emits NO error frame and NO event (IAS-A6)',
  );

  delete process.env.LW_WS_MSG_PER_WINDOW;
  delete process.env.LW_WS_RATE_WINDOW_MS;
});

// ── the confused-deputy hole (2026-08-06) ──────────────────────────────────
//
// `actorForUser` returned `LW_CHANNEL_DEFAULT_ACTOR ?? '1'` for any
// authenticated user absent from the map, so every unmapped user was bound to
// the SAME subject — two humans acting as one actor, stamped by the server. A
// red-team pass called this the load-bearing hole and downgraded the
// confused-deputy guard because of it: a keyed MAC over a subject is a lock on
// the wrong door while the caller can already BE that subject.
//
// Nothing tested it, which is why it survived a security review that NAMED it.

// `E3` re-pointed this at the durable binding, which is what the assertion
// below asked for in its own message: *"Re-point it at the binding when that
// lookup lands, and close the row."* The confused-deputy arms survive
// unchanged — they are what the row was protecting — and three arms are added
// for the source that replaced the map.

test('an unmapped authenticated user is bound to NOBODY, not to a default actor', () => {
  const prevMap = process.env.LW_CHANNEL_ACTOR_MAP;
  const prevDefault = process.env.LW_CHANNEL_DEFAULT_ACTOR;
  // The default is set on purpose: if the fallback ever comes back, this env
  // var is what it would read, so the test would go green again without it.
  process.env.LW_CHANNEL_DEFAULT_ACTOR = '1';
  process.env.LW_CHANNEL_ACTOR_MAP = 'alice:7';

  const room = new ChannelRoom() as unknown as {
    actorFromDevMap(u: string): string | undefined;
  };

  assert.equal(room.actorFromDevMap('alice'), '7', 'an explicit mapping still resolves');
  assert.equal(
    room.actorFromDevMap('mallory'),
    undefined,
    'an authenticated user with no binding must drive nobody — a default here is ' +
      'the server itself asserting that a stranger is entity 1.',
  );
  assert.notEqual(
    room.actorFromDevMap('mallory'),
    room.actorFromDevMap('alice'),
    'two users must never resolve to one subject',
  );

  if (prevMap === undefined) delete process.env.LW_CHANNEL_ACTOR_MAP;
  else process.env.LW_CHANNEL_ACTOR_MAP = prevMap;
  if (prevDefault === undefined) delete process.env.LW_CHANNEL_DEFAULT_ACTOR;
  else process.env.LW_CHANNEL_DEFAULT_ACTOR = prevDefault;
});

// ── `E3` — the env map is no longer a source unless a developer says so ────

test('with NOTHING configured the join is refused, not seated as a spectator', async () => {
  const prevMap = process.env.LW_CHANNEL_ACTOR_MAP;
  const prevDev = process.env.LW_WS_DEV_ALLOW_STATIC;
  const prevUrl = process.env.LW_WORLD_SERVICE_URL;
  // The map is POPULATED and would answer — that is the point. If it is ever
  // consulted without the dev flag, this user resolves to entity 7 and the
  // assertion below goes green for the wrong reason.
  process.env.LW_CHANNEL_ACTOR_MAP = 'alice:7';
  delete process.env.LW_WS_DEV_ALLOW_STATIC;
  delete process.env.LW_WORLD_SERVICE_URL;

  const room = new ChannelRoom() as unknown as {
    actorOf: Map<string, string>;
    opts: unknown;
    onJoin(c: unknown): Promise<void>;
  };
  room.opts = { realityId: 'r1', channelId: 'c1' };
  const sent: Array<[string, unknown]> = [];
  const client = {
    sessionId: 's1',
    auth: { userId: 'alice' },
    send: (t: string, p: unknown) => sent.push([t, p]),
    leave: () => {},
  };

  let threw: unknown;
  await room.onJoin(client).catch((e) => {
    threw = e;
  });

  assert.ok(
    threw,
    'an unconfigured room must REFUSE the join, not answer from the env map. This ' +
      'assertion holds the safe state for D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT: ' +
      'E3 made the transport ASK (world-service /internal/v1/actor-control/subject), ' +
      'but every test of that path stubs `fetch`, and a read that has never reached a ' +
      'real service is the shape meta_read_audit was in for four months — four layers ' +
      'each correct-looking, with an empty table underneath. The row closes at E5, on ' +
      'a live run, not here.',
  );
  assert.equal(room.actorOf.has('s1'), false, 'and it must bind nobody');
  assert.equal(
    sent.find(([t]) => t === 'w1.frame'),
    undefined,
    'no frame either — seating them with `self: null` would say "you drive nobody" ' +
      'when the truth is "nothing was asked"',
  );

  if (prevMap === undefined) delete process.env.LW_CHANNEL_ACTOR_MAP;
  else process.env.LW_CHANNEL_ACTOR_MAP = prevMap;
  if (prevDev !== undefined) process.env.LW_WS_DEV_ALLOW_STATIC = prevDev;
  if (prevUrl !== undefined) process.env.LW_WORLD_SERVICE_URL = prevUrl;
});

test('onJoin binds no session entry when the user drives nobody', async () => {
  const prevMap = process.env.LW_CHANNEL_ACTOR_MAP;
  const prevDev = process.env.LW_WS_DEV_ALLOW_STATIC;
  process.env.LW_CHANNEL_ACTOR_MAP = 'alice:7';
  // `E3` — the dev map is now a DECLARED binding, not the default one. The
  // spectator case this test is about is unchanged; reaching it just has to be
  // asked for now.
  process.env.LW_WS_DEV_ALLOW_STATIC = '1';

  const room = new ChannelRoom() as unknown as {
    actorOf: Map<string, string>;
    opts: unknown;
    onJoin(c: unknown): Promise<void>;
  };
  // `opts` is normally set by onCreate; onJoin reads realityId/channelId for the
  // bind ack. Stubbed rather than booting a room, because the subject here is
  // the BINDING, not the handshake.
  room.opts = { realityId: 'r1', channelId: 'c1' };
  const sent: Array<[string, unknown]> = [];
  const client = {
    sessionId: 's1',
    auth: { userId: 'mallory' },
    send: (t: string, p: unknown) => sent.push([t, p]),
    leave: () => {},
  };
  await room.onJoin(client);

  // The MAP is what makes `handleSubmit`'s `no_actor_bound` reachable. An entry
  // here — any entry — is the hole, because submit reads exactly this.
  assert.equal(room.actorOf.has('s1'), false, 'no actor entry for an unbound user');

  const frame = sent.find(([t]) => t === 'w1.frame');
  assert.ok(frame, 'the room still sends a frame — the user may watch');
  assert.equal(
    (frame![1] as { self: unknown }).self,
    null,
    '`self` must be null, not a fabricated entity: the frame is what the client ' +
      'renders as "you"',
  );

  if (prevMap === undefined) delete process.env.LW_CHANNEL_ACTOR_MAP;
  else process.env.LW_CHANNEL_ACTOR_MAP = prevMap;
  if (prevDev === undefined) delete process.env.LW_WS_DEV_ALLOW_STATIC;
  else process.env.LW_WS_DEV_ALLOW_STATIC = prevDev;
});
