// The THIRD conformance side of `contracts/game-wire/`.
//
// commit-service::wire (Rust) and game-server/src/wire (TS) already assert
// against the schema; the browser is the side that actually renders to a
// human, so a drift here is the one a user sees. Same discipline: assert
// against the SCHEMA FILE, never against the other implementations.
//
// ⚠ This is `frontend-game` (the MMORPG client). `frontend/` is the separate
// novel-workflow SPA and shares none of this.

import { describe, expect, it, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  consumedTurn,
  outcomeLines,
  CHANNEL_MESSAGES,
  type DiscardDetail,
  type OutcomeKind,
  type TurnOutcome,
} from '@/net/channel-protocol';
import { useChannelStore } from '@/store/channel-store';

const schema = JSON.parse(
  readFileSync(resolve(__dirname, '../../contracts/game-wire/turn.schema.json'), 'utf8'),
) as {
  $defs: {
    TurnOutcome: { properties: { kind: { enum: OutcomeKind[] } } };
    DiscardDetail: { properties: { reason: { enum: string[] } } };
    TurnSubmit: { properties: Record<string, unknown>; required: string[] };
  };
};

describe('game-wire conformance (browser side)', () => {
  it('OutcomeKind is exactly the schema enum', () => {
    const allowed = schema.$defs.TurnOutcome.properties.kind.enum;
    const mine: OutcomeKind[] = ['resolved', 'discarded', 'rejected'];
    expect([...mine].sort()).toEqual([...allowed].sort());
  });

  it('DiscardReason is exactly the 5-variant sim-core set', () => {
    const allowed = schema.$defs.DiscardDetail.properties.reason.enum;
    expect(allowed).toHaveLength(5);
    for (const r of ['duplicate', 'precondition_failed', 'superseded', 'expired', 'quarantined']) {
      expect(allowed).toContain(r);
    }
  });

  it('TurnSubmit carries NO actor field — the room stamps identity', () => {
    // The confused-deputy guard, asserted at the contract: if `actor` ever
    // appears here, a client could act as another player.
    const props = Object.keys(schema.$defs.TurnSubmit.properties);
    expect(props).not.toContain('actor');
    expect(props).not.toContain('actor_entity_id');
    expect(schema.$defs.TurnSubmit.required).toContain('client_request_id');
  });
});

describe('EVT-V4 turn semantics in the UI layer', () => {
  const outcome = (kind: OutcomeKind, turn: string): TurnOutcome =>
    ({
      channel_event_id: '10',
      kind,
      turn_number: turn,
      detail:
        kind === 'resolved'
          ? { events: ['1 strikes 2 for 10 (30 left)'] }
          : kind === 'discarded'
            ? { reason: 'superseded', user_message: 'The encounter ended.' }
            : { stage: 'idempotency', user_message: 'duplicate' },
    }) as TurnOutcome;

  it('only a resolved outcome consumes the turn', () => {
    expect(consumedTurn(outcome('resolved', '2'))).toBe(true);
    expect(consumedTurn(outcome('discarded', '1'))).toBe(false);
    expect(consumedTurn(outcome('rejected', '1'))).toBe(false);
  });

  it('renders the right line for each kind', () => {
    expect(outcomeLines(outcome('resolved', '2'))).toEqual(['1 strikes 2 for 10 (30 left)']);
    expect(outcomeLines(outcome('discarded', '1'))).toEqual(['The encounter ended.']);
    expect(outcomeLines(outcome('rejected', '1'))).toEqual(['duplicate']);
  });

  it('a discarded outcome is NOT reported as rejected', () => {
    // Telling a player "not allowed" when the truth is "the world moved" is a
    // lie that invites the wrong correction.
    const d = outcome('discarded', '1');
    expect((d.detail as DiscardDetail).reason).toBe('superseded');
    expect(d.kind).not.toBe('rejected');
  });
});

describe('channel store', () => {
  beforeEach(() => useChannelStore.getState().reset());

  it('copies turn_number from the commit — never increments locally', () => {
    const s = useChannelStore.getState();
    s.applyOutcome(outcomeOf('resolved', '1'));
    expect(useChannelStore.getState().turnNumber).toBe('1');
    // A rejection arrives: the turn must STAY, not advance.
    useChannelStore.getState().applyOutcome(outcomeOf('rejected', '1'));
    expect(useChannelStore.getState().turnNumber).toBe('1');
    useChannelStore.getState().applyOutcome(outcomeOf('resolved', '2'));
    expect(useChannelStore.getState().turnNumber).toBe('2');
  });

  it('clears the in-flight marker on ANY outcome, not just resolved', () => {
    // Kill-mutation: clear only on `resolved` → the UI wedges forever the
    // first time a rejection comes back.
    useChannelStore.getState().markSubmitted('req-1');
    expect(useChannelStore.getState().pending).toBe('req-1');
    useChannelStore.getState().applyOutcome(outcomeOf('rejected', '1'));
    expect(useChannelStore.getState().pending).toBeNull();
    expect(useChannelStore.getState().lastConsumedTurn).toBe(false);
  });

  it('bounds the log', () => {
    for (let i = 0; i < 260; i++) useChannelStore.getState().applyOutcome(outcomeOf('resolved', '1'));
    expect(useChannelStore.getState().log.length).toBeLessThanOrEqual(200);
  });

  it('exposes the wire message names in one place', () => {
    expect(CHANNEL_MESSAGES.outcome).toBe('turn.outcome');
    expect(CHANNEL_MESSAGES.submit).toBe('turn.submit');
  });
});

function outcomeOf(kind: OutcomeKind, turn: string): TurnOutcome {
  return {
    channel_event_id: '1',
    kind,
    turn_number: turn,
    detail: kind === 'resolved' ? { events: ['x'] } : { stage: 's', user_message: 'm' },
  } as TurnOutcome;
}
