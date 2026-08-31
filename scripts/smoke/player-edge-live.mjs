// `E5` — the transport's resolver against a REAL world-service.
//
// # What this proves that nothing else does
//
// `services/game-server/src/ws/subject.test.ts` has ten arms and every one of
// them stubs `globalThis.fetch`. That is the right way to test the room's
// branching, and it is worth nothing as evidence that the HTTP call works:
// a wrong path, a wrong header name, a wrong request shape or a response the
// parser mis-reads all pass a stubbed test and fail on the wire.
//
// `D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT` is closed by THIS, not by the unit
// suite. The row has been open since 2026-08-06 and its whole subject is
// whether the transport actually reads the durable binding.
//
// # It is READ-ONLY, and that is why it needs no throwaway database
//
// It resolves bindings that already exist and writes nothing, so it runs
// against whatever stack you point it at. Give it a reality and two users —
// one who drives an actor there and one whose binding was revoked — and it
// checks that the resolver tells them apart. The revoked user is not optional
// decoration: a resolver that ignored `revoked_at` answers identically for
// both, and the driving case alone cannot show that it does not.
//
//   node scripts/smoke/player-edge-live.mjs \
//     --url http://127.0.0.1:7137 --token <internal> \
//     --reality <uuid> --driver <uuid> [--revoked <uuid>] [--expect-entity 1]
//
// world-service is NOT in infra/docker-compose.yml, so start it from source
// first (the same way `E1`'s smoke did) and pass its address here.

import { HttpSubjectResolver } from '../../services/game-server/dist/ws/subject.js';

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  if (i >= 0 && process.argv[i + 1]) return process.argv[i + 1];
  if (fallback !== undefined) return fallback;
  console.error(`missing --${name}`);
  process.exit(2);
}

const url = arg('url');
const token = arg('token');
const reality = arg('reality');
const driver = arg('driver');
const revoked = arg('revoked', '');
const expectEntity = arg('expect-entity', '');

const resolver = new HttpSubjectResolver(url, token);
let failures = 0;

function check(label, ok, detail) {
  console.log(`  ${ok ? 'OK  ' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures++;
}

console.log(`player-edge live smoke -> ${url}`);

// 1 — the driver resolves, over real HTTP, through both database tiers.
const got = await resolver.resolve(reality, driver);
console.log(`  driver   -> ${JSON.stringify(got)}`);
check('the driver resolves to an actor', got.kind === 'driving', got.detail ?? got.kind);
if (expectEntity) {
  check(
    `entity_id is ${expectEntity}`,
    got.kind === 'driving' && got.entityId === expectEntity,
    got.kind === 'driving' ? got.entityId : got.kind,
  );
}

// 2 — a revoked binding is NOBODY, decided by the server, not by us.
if (revoked) {
  const r = await resolver.resolve(reality, revoked);
  console.log(`  revoked  -> ${JSON.stringify(r)}`);
  check('a revoked binding drives nobody', r.kind === 'nobody', r.kind);
}

// 3 — a user with no binding at all. Generated rather than passed, because the
// interesting property is that an ARBITRARY id gets nothing.
const stranger = '00000000-dead-4000-8000-00000000beef';
const s = await resolver.resolve(reality, stranger);
console.log(`  stranger -> ${JSON.stringify(s)}`);
check('an unbound user drives nobody', s.kind === 'nobody', s.kind);

// 4 — an unregistered reality is the WORLD refusing, not "you drive nobody".
// The distinction that only a real server can demonstrate: our own code maps a
// 400 to `realityClosed`, but whether world-service sends a 400 at all is its
// decision and this is the only place the two meet.
const nowhere = await resolver.resolve('11111111-2222-4333-8444-999999999999', driver);
console.log(`  no-world -> ${JSON.stringify(nowhere)}`);
check('an unregistered reality is refused, not reported as spectating',
  nowhere.kind === 'realityClosed', nowhere.kind);

// 5 — a bad token must be OURS, not a statement about the world.
const wrong = new HttpSubjectResolver(url, 'not-the-token');
const w = await wrong.resolve(reality, driver);
console.log(`  bad-token-> ${JSON.stringify(w)}`);
check('a rejected internal token reads as unavailable', w.kind === 'unavailable', w.kind);

console.log('');
console.log(failures === 0 ? 'PLAYER-EDGE LIVE: PASS' : `PLAYER-EDGE LIVE: ${failures} FAILURE(S)`);

// `process.exitCode`, NOT `process.exit()`.
//
// The first version called `process.exit()` here and Node aborted on Windows
// with `Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)` — AFTER printing
// PASS — so the shell saw 127 on a run where every arm passed. Fail-safe rather
// than fail-open, but it is still an exit code that does not mean what it says,
// and a smoke whose exit code is noise is a smoke nobody can put in CI.
//
// The cause is `fetch`'s keep-alive pool: tearing the process down under it
// kills sockets mid-close. Setting the code and letting the loop drain lets the
// pool time out on its own, which costs a few seconds and produces an exit
// status that is actually about the assertions.
process.exitCode = failures === 0 ? 0 : 1;
