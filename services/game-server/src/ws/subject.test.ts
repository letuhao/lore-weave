import assert from 'node:assert/strict';
import test from 'node:test';

import { HttpSubjectResolver, isUserRefId, subjectResolverFromEnv } from './subject.js';

// `E3` — the resolver that replaced `LW_CHANNEL_ACTOR_MAP`.
//
// Every arm here is about a DISTINCTION, not a happy path. The recurring defect
// on this seam is not "the lookup returned the wrong actor" — it is two
// different facts arriving as one, so that an outage reads as "you drive
// nobody" and a player is silently demoted with nothing in the log.

/** Stand in for `fetch` and restore it afterwards. */
function withFetch<T>(
  impl: (url: string, init: RequestInit) => Promise<Response>,
  body: () => Promise<T>,
): Promise<T> {
  const real = globalThis.fetch;
  globalThis.fetch = impl as unknown as typeof fetch;
  return body().finally(() => {
    globalThis.fetch = real;
  });
}

const R = '11111111-2222-4333-8444-555566667777';
const U = 'bbbb1111-2222-4333-8444-555566667777';

function json(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

test('a live binding resolves to the island entity id', async () => {
  await withFetch(
    async (url, init) => {
      assert.match(url, /\/internal\/v1\/actor-control\/subject$/);
      assert.equal((init.headers as Record<string, string>)['X-Internal-Token'], 'tok');
      // SEALED-SUBJECT: the request names the reality and the USER. It must
      // never carry an actor — a subject on the wire is one that can be forged,
      // and "the client asserts, the server verifies" is the class P3 killed.
      const sent = JSON.parse(String(init.body));
      assert.deepEqual(Object.keys(sent).sort(), ['reality_id', 'user_ref_id']);
      return json(200, { self: { actor_id: 'a-1', entity_id: 7 } });
    },
    async () => {
      const got = await new HttpSubjectResolver('http://world:7120', 'tok').resolve(R, U);
      assert.deepEqual(got, { kind: 'driving', entityId: '7', actorId: 'a-1' });
    },
  );
});

test('`self: null` is NOBODY — a normal answer, not a failure', async () => {
  await withFetch(
    async () => json(200, { self: null }),
    async () => {
      const got = await new HttpSubjectResolver('http://world:7120', 'tok').resolve(R, U);
      assert.deepEqual(got, { kind: 'nobody' });
    },
  );
});

test('a 400 is the WORLD refusing, and is not confused with an outage', async () => {
  await withFetch(
    async () => new Response('reality is frozen', { status: 400 }),
    async () => {
      const got = await new HttpSubjectResolver('http://world:7120', 'tok').resolve(R, U);
      assert.equal(got.kind, 'realityClosed');
    },
  );
});

test('an unreachable control plane is UNAVAILABLE, never `nobody`', async () => {
  await withFetch(
    async () => {
      throw new Error('ECONNREFUSED');
    },
    async () => {
      const got = await new HttpSubjectResolver('http://world:7120', 'tok').resolve(R, U);
      assert.equal(
        got.kind,
        'unavailable',
        'an outage reported as `nobody` silently turns every player into a spectator',
      );
    },
  );
});

test('a 401 is OURS, not the world being closed', async () => {
  await withFetch(
    async () => new Response('', { status: 401 }),
    async () => {
      const got = await new HttpSubjectResolver('http://world:7120', 'tok').resolve(R, U);
      assert.equal(
        got.kind,
        'unavailable',
        'a rejected internal token is a deployment problem; calling it "the world is ' +
          'closed" sends an operator to look at the reality instead',
      );
    },
  );
});

test('a non-UUID principal never leaves the process', async () => {
  let called = false;
  await withFetch(
    async () => {
      called = true;
      return json(200, { self: null });
    },
    async () => {
      // What `LW_WS_DEV_ALLOW_STATIC` auth produces: `dev:abcd`, not a
      // `user_ref_id`. Sending it would be a 422 from another service, and the
      // refusal would name the wrong cause.
      const got = await new HttpSubjectResolver('http://world:7120', 'tok').resolve(R, 'dev:abcd');
      // Asserted FIRST because it is the stronger claim: not merely that the
      // answer is safe, but that the malformed id never left the process.
      assert.equal(called, false, 'no request should have been made at all');
      assert.equal(got.kind, 'unavailable');
    },
  );
});

test('a negative entity_id is refused rather than passed through', async () => {
  await withFetch(
    async () => json(200, { self: { actor_id: 'a-1', entity_id: -1 } }),
    async () => {
      const got = await new HttpSubjectResolver('http://world:7120', 'tok').resolve(R, U);
      assert.equal(
        got.kind,
        'unavailable',
        'the island types an entity as u64; a negative here is registry corruption, ' +
          'and `String(-1)` would be a key that matches nothing in the roster',
      );
    },
  );
});

test('a response with no `self` key is NOBODY, and it is loud', async () => {
  // Wire-contract drift: the Rust side renames the field and the key vanishes.
  // Refusing to act is right; doing it silently is what the serde test on the
  // other side exists to prevent, so this one records that both ends care.
  await withFetch(
    async () => json(200, { reality_id: R }),
    async () => {
      const got = await new HttpSubjectResolver('http://world:7120', 'tok').resolve(R, U);
      assert.deepEqual(got, { kind: 'nobody' });
    },
  );
});

test('isUserRefId accepts a uuid and rejects what the dev auth path produces', () => {
  assert.equal(isUserRefId(U), true);
  assert.equal(isUserRefId('dev:abcd'), false);
  assert.equal(isUserRefId('alice'), false);
  assert.equal(isUserRefId(''), false);
  // Non-vacuity: a matcher that rejected everything would pass every arm above.
  assert.equal(isUserRefId('00000000-0000-4000-8000-000000000000'), true);
});

test('the resolver is absent unless BOTH the url and the token are configured', () => {
  const prevUrl = process.env.LW_WORLD_SERVICE_URL;
  const prevTok = process.env.LOREWEAVE_INTERNAL_TOKEN;
  try {
    delete process.env.LW_WORLD_SERVICE_URL;
    delete process.env.LOREWEAVE_INTERNAL_TOKEN;
    assert.equal(subjectResolverFromEnv(), undefined);

    process.env.LW_WORLD_SERVICE_URL = 'http://world:7120';
    assert.equal(subjectResolverFromEnv(), undefined, 'a url with no token is not configuration');

    process.env.LOREWEAVE_INTERNAL_TOKEN = 'tok';
    assert.ok(subjectResolverFromEnv(), 'both present — the resolver exists');

    // A blank value is absence, not configuration. Compose writes empty strings
    // for unset variables, so `?? ''` alone would have built a resolver that
    // sends an empty token to every call.
    process.env.LW_WORLD_SERVICE_URL = '   ';
    assert.equal(subjectResolverFromEnv(), undefined);
  } finally {
    if (prevUrl === undefined) delete process.env.LW_WORLD_SERVICE_URL;
    else process.env.LW_WORLD_SERVICE_URL = prevUrl;
    if (prevTok === undefined) delete process.env.LOREWEAVE_INTERNAL_TOKEN;
    else process.env.LOREWEAVE_INTERNAL_TOKEN = prevTok;
  }
});
