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
