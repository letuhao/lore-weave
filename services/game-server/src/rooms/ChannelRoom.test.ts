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
  (room as unknown as { actorOf: Map<string, string> }).actorOf.set('s1', '1');
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
