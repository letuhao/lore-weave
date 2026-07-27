import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  projectTurnOutcome,
  toU64String,
  type CommittedEvent,
  type DiscardDetail,
  type OutcomeKind,
  type RejectDetail,
} from './turnOutcome.js';

// The schema is the SoT both languages check against — never each other.
// Path is resolved from the COMPILED file's location (dist/wire/), so it must
// climb out of dist as well as out of the service.
const here = dirname(fileURLToPath(import.meta.url));
const schema = JSON.parse(
  readFileSync(
    resolve(here, '../../../../contracts/game-wire/turn.schema.json'),
    'utf8',
  ),
) as {
  $defs: {
    TurnOutcome: { properties: { kind: { enum: OutcomeKind[] } } };
    DiscardDetail: { properties: { reason: { enum: string[] } } };
  };
};

// ── the polyglot mirror checks (the whole point of the contract) ──

test('kind values are exactly the schema enum — the Rust producer emits the same set', () => {
  const allowed = schema.$defs.TurnOutcome.properties.kind.enum;
  const mine: OutcomeKind[] = ['resolved', 'discarded', 'rejected'];
  assert.deepEqual([...mine].sort(), [...allowed].sort());
  // Kill-mutation: add a 4th TS kind (or rename one) without touching the
  // schema — this reds, and so does the Rust side's mirror of it.
  assert.equal(allowed.length, 3);
});

test('discard reasons are exactly the 5-variant sim-core set', () => {
  const allowed = schema.$defs.DiscardDetail.properties.reason.enum;
  assert.equal(allowed.length, 5, 'sim-core has FIVE discard reasons since S1b');
  for (const r of ['duplicate', 'precondition_failed', 'superseded', 'expired', 'quarantined']) {
    assert.ok(allowed.includes(r), `${r} missing from the schema enum`);
  }
});

// ── CWC-A2: the 2^53 corruption class ──

test('u64 strings pass through untouched', () => {
  assert.equal(toU64String('9007199254740993', 'x'), '9007199254740993');
  assert.equal(toU64String(42, 'x'), '42');
});

test('a number beyond 2^53 is REFUSED, not laundered', () => {
  // 2^53 + 1 cannot be represented; by the time it is a JS number the damage
  // is done. Passing it on would hide the producer's bug downstream.
  // Kill-mutation: accept any number → this test reds.
  assert.throws(() => toU64String(9007199254740993, 'channel_event_id'), /precision was already lost/);
});

test('a non-numeric string is refused', () => {
  assert.throws(() => toU64String('12x', 'turn_number'), /not a u64 decimal string/);
  assert.throws(() => toU64String(undefined, 'turn_number'), /missing/);
});

// ── CWC-A6 / EVT-V4: three kinds, and only one consumes a turn ──

const committed = (
  event_type: string,
  channel_event_id: string,
  turn_number: string,
  payload: Record<string, unknown> = {},
): CommittedEvent => ({
  event_type,
  channel_event_id,
  payload,
  metadata: { event_category: 'T6', turn_number },
});

test('the live spine log shape projects correctly: ce3 turn1 / ce4 rejected turn1 / ce5 turn2', () => {
  // This is the ACTUAL committed sequence from the 2026-07-27 S3b smoke.
  const resolved1 = projectTurnOutcome(committed('turn.resolved', '3', '1'))!;
  const rejected = projectTurnOutcome(
    committed('proposal.rejected', '4', '1', {
      rejected_at_stage: 'decision-vocabulary',
      reason: "tool 'summon_dragon' is not in the closed vocabulary",
    }),
  )!;
  const resolved2 = projectTurnOutcome(committed('turn.resolved', '5', '2'))!;

  assert.equal(resolved1.kind, 'resolved');
  assert.equal(rejected.kind, 'rejected');
  assert.equal(resolved2.kind, 'resolved');
  // EVT-V4: the rejection did NOT advance the turn — the client must not
  // burn a turn slot in its UI either.
  assert.equal(resolved1.turn_number, '1');
  assert.equal(rejected.turn_number, '1');
  assert.equal(resolved2.turn_number, '2');
  assert.equal((rejected.detail as RejectDetail).stage, 'decision-vocabulary');
});

test('discarded is NOT rejected — distinct kind, distinct detail shape', () => {
  const d = projectTurnOutcome(
    committed('turn.discarded', '7', '2', {
      reason: 'superseded',
      user_message: 'The encounter ended.',
    }),
  )!;
  assert.equal(d.kind, 'discarded');
  assert.equal((d.detail as DiscardDetail).reason, 'superseded');
  // Kill-mutation: map discarded onto rejected — the UI would tell the player
  // "not allowed" when the truth is "the world moved", inviting a re-issue.
  assert.notEqual(d.kind, 'rejected');
});

test('non-outcome events project to null rather than a blank frame', () => {
  assert.equal(projectTurnOutcome(committed('entity.spawned', '9', '2')), null);
});

test('the consumer never recomputes turn_number — it reads the commit', () => {
  // A stream that redelivers ce4 (at-least-once) must project identically;
  // a consumer holding its own counter would drift on redelivery.
  const a = projectTurnOutcome(committed('proposal.rejected', '4', '1', {}))!;
  const b = projectTurnOutcome(committed('proposal.rejected', '4', '1', {}))!;
  assert.deepEqual(a, b);
});
