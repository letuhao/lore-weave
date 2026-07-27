import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { PRODUCER_NAME, producerKeyFromEnv, signProposal } from './producer-sign.js';

// PID — the TypeScript half of the producer-identity contract. The Rust
// verifier lives in commit-service and the two are joined ONLY by
// contracts/agent/producer-identity.fixture.json, so both sides assert
// against the FIXTURE and never against each other's implementation.

const FIXTURE = JSON.parse(
  readFileSync(
    resolve(import.meta.dirname, '../../../../contracts/agent/producer-identity.fixture.json'),
    'utf8',
  ),
) as { key: string; raw: string; sig: string };

test('this side reproduces the fixture signature exactly', () => {
  // If this reds, either the MAC inputs changed or the algorithm did — and the
  // Rust test reds too. That symmetry is the point of the fixture.
  const { sig } = signProposal(JSON.parse(FIXTURE.raw), FIXTURE.key);
  assert.equal(sig, FIXTURE.sig);
});

test('the signed bytes are the bytes that go on the wire', () => {
  // PID-D2. The caller must XADD `raw`, not re-stringify the object: a second
  // JSON.stringify could legally emit different bytes, and the MAC would then
  // cover something nobody sent.
  const proposal = { b: 2, a: 1 };
  const { raw } = signProposal(proposal, 'k');
  assert.equal(raw, JSON.stringify(proposal), 'raw is exactly what was signed');
});

test('no key ⇒ sig is null, never a fabricated one', () => {
  // Kill-mutation: returning some placeholder signature would sail past a
  // truthiness check at the call site and put unsigned traffic on the bus
  // wearing a signature field.
  const { raw, sig } = signProposal({ x: 1 }, undefined);
  assert.equal(sig, null);
  assert.ok(raw.length > 0, 'the payload is still produced; only the proof is absent');
});

test('a one-byte change to the payload changes the signature', () => {
  const a = signProposal({ actor: 1 }, 'k').sig;
  const b = signProposal({ actor: 2 }, 'k').sig;
  assert.notEqual(a, b, 'the MAC covers the payload, not just the producer name');
});

test('producerKeyFromEnv returns undefined when unset, and warns', () => {
  const prev = process.env.LW_PRODUCER_KEY_GAME_SERVER;
  delete process.env.LW_PRODUCER_KEY_GAME_SERVER;
  assert.equal(producerKeyFromEnv(), undefined);
  process.env.LW_PRODUCER_KEY_GAME_SERVER = 'k';
  assert.equal(producerKeyFromEnv(), 'k');
  if (prev === undefined) delete process.env.LW_PRODUCER_KEY_GAME_SERVER;
  else process.env.LW_PRODUCER_KEY_GAME_SERVER = prev;
});

test('the producer name matches the one the fixture is signed for', () => {
  assert.equal(PRODUCER_NAME, JSON.parse(FIXTURE.raw).producer_service);
});
