import { describe, it, expect } from 'vitest';
import {
  actionsForRunStatus, canReviewUnit, isBudgetDanger, isHeartbeatStale,
  breakerSeverity, keyToUnitReviewAction, REVIEWABLE_RUN_STATUSES,
} from '../fsm';
import type { AuthoringRunStatus, AuthoringRunUnitStatus } from '../types';

describe('actionsForRunStatus (FSM-legal action set per real router wiring)', () => {
  const cases: Array<[AuthoringRunStatus, string[]]> = [
    ['draft', ['gate']],
    ['gated', ['start', 'close']],
    ['running', ['pause']],
    ['paused', ['resume', 'close', 'revert-all']],
    ['failed', ['close', 'revert-all']],
    ['report_ready', ['close', 'revert-all']],
    ['closed', []],
  ];
  it.each(cases)('%s -> %j', (status, expected) => {
    expect(actionsForRunStatus(status)).toEqual(expected);
  });
});

describe('canReviewUnit (D8 — the single most correctness-critical rule)', () => {
  const drafted: AuthoringRunUnitStatus = 'drafted';
  it('allows accept/reject only when BOTH the run is reviewable AND the unit is drafted', () => {
    for (const status of REVIEWABLE_RUN_STATUSES) {
      expect(canReviewUnit(status, drafted)).toBe(true);
    }
  });
  it('blocks review while the run is running, gated, draft, or closed — even for a drafted unit', () => {
    for (const status of ['running', 'gated', 'draft', 'closed'] as AuthoringRunStatus[]) {
      expect(canReviewUnit(status, drafted)).toBe(false);
    }
  });
  it('blocks review of a non-drafted unit even in a reviewable run status', () => {
    for (const unitStatus of ['pending', 'accepted', 'rejected', 'failed'] as AuthoringRunUnitStatus[]) {
      expect(canReviewUnit('paused', unitStatus)).toBe(false);
    }
  });
});

describe('isBudgetDanger (D11 — red at >=85% spent)', () => {
  it('is false under 85%', () => expect(isBudgetDanger(0.84, 1)).toBe(false));
  it('is true at exactly 85%', () => expect(isBudgetDanger(0.85, 1)).toBe(true));
  it('is true over 85%', () => expect(isBudgetDanger(3.79, 4)).toBe(true));
  it('is false with a zero/invalid budget (never divide by zero into a false danger)', () => expect(isBudgetDanger(5, 0)).toBe(false));
});

describe('isHeartbeatStale (D11 — placeholder threshold, only meaningful while running)', () => {
  const now = Date.parse('2026-07-05T12:00:00Z');
  it('is always false outside status=running', () => {
    expect(isHeartbeatStale('paused', null, now)).toBe(false);
    expect(isHeartbeatStale('failed', new Date(now - 999_000).toISOString(), now)).toBe(false);
  });
  it('is true for a running run with no heartbeat at all', () => {
    expect(isHeartbeatStale('running', null, now)).toBe(true);
  });
  it('is false for a running run with a fresh heartbeat', () => {
    expect(isHeartbeatStale('running', new Date(now - 3_000).toISOString(), now)).toBe(false);
  });
  it('is true for a running run whose heartbeat is older than the threshold', () => {
    expect(isHeartbeatStale('running', new Date(now - 41_000).toISOString(), now)).toBe(true);
  });
});

describe('breakerSeverity', () => {
  it('is ok when empty/absent', () => {
    expect(breakerSeverity({})).toBe('ok');
    expect(breakerSeverity(null)).toBe('ok');
    expect(breakerSeverity(undefined)).toBe('ok');
  });
  it('is danger for a hard failure reason', () => {
    expect(breakerSeverity({ reason: 'unit_failed' })).toBe('danger');
    expect(breakerSeverity({ reason: 'driver_crashed' })).toBe('danger');
  });
  it('is warn for an intentional pause-for-review reason', () => {
    expect(breakerSeverity({ reason: 'budget' })).toBe('warn');
    expect(breakerSeverity({ reason: 'critic_severe' })).toBe('warn');
  });
  it('is warn (not silently ok) for an off-contract reason string', () => {
    expect(breakerSeverity({ reason: 'something_new' })).toBe('warn');
  });
});

describe('keyToUnitReviewAction (D10 keyboard triage)', () => {
  it('maps the documented keys', () => {
    expect(keyToUnitReviewAction('a')).toBe('accept');
    expect(keyToUnitReviewAction('r')).toBe('reject');
    expect(keyToUnitReviewAction('ArrowRight')).toBe('next');
    expect(keyToUnitReviewAction('n')).toBe('next');
    expect(keyToUnitReviewAction('ArrowLeft')).toBe('prev');
    expect(keyToUnitReviewAction('p')).toBe('prev');
  });
  it('is a no-op (null, not a throw) for an unrelated key', () => {
    expect(keyToUnitReviewAction('Escape')).toBeNull();
    expect(keyToUnitReviewAction('Tab')).toBeNull();
  });
});
