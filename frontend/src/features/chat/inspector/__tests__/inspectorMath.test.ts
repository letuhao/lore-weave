import { describe, it, expect } from 'vitest';
import type { ContextTracePoint, TraceSpanFrame } from '../../types';
import {
  computeKpis,
  filterSpans,
  filterTurns,
  gaugeState,
  kfmt,
  spanDeltaKind,
  statusMeta,
  turnReductionPct,
} from '../inspectorMath';

// Verify-by-EFFECT for the Inspector's pure core — the math the gauge color, the
// KPIs, and the filters read. Not "does a function exist" but "does compiled>target
// yield over-target", "does the gated filter drop non-gated turns", etc.

function pt(seq: number, over: Partial<ContextTracePoint['frame']>, msg = 'hi'): ContextTracePoint {
  return {
    sequence_num: seq,
    created_at: '2026-07-04T00:00:00Z',
    input_tokens: over.used_tokens ?? 100,
    output_tokens: 10,
    user_message: msg,
    frame: {
      used_tokens: 100,
      context_length: 131072,
      effective_limit: 128000,
      pct: 0.1,
      target: 32000,
      status_flags: [],
      ...over,
    },
  };
}

describe('gaugeState', () => {
  it('under target → under', () => {
    expect(gaugeState(1000, 32000, 131072)).toBe('under');
  });
  it('over target but under ceiling → over-target', () => {
    expect(gaugeState(40000, 32000, 131072)).toBe('over-target');
  });
  it('over ceiling → over-ceiling (worst wins)', () => {
    expect(gaugeState(140000, 32000, 131072)).toBe('over-ceiling');
  });
  it('null target/ceiling degrade to under (never a bogus warning)', () => {
    expect(gaugeState(9999, null, null)).toBe('under');
  });
});

describe('computeKpis', () => {
  it('averages reduction over turns WITH a raw baseline and sums saved', () => {
    const points = [
      pt(1, { used_tokens: 40, raw_tokens: 100, reduction_pct: 0.6 }),
      pt(2, { used_tokens: 50, raw_tokens: 200, reduction_pct: 0.75 }),
      pt(3, { used_tokens: 100 }), // no raw baseline → excluded from avg + saved
    ];
    const k = computeKpis(points);
    expect(k.tokensSaved).toBe(60 + 150);
    expect(k.avgReductionPct).toBeCloseTo(((0.6 + 0.75) / 2) * 100, 5);
    expect(k.modelWindow).toBe(131072);
    expect(k.turnCount).toBe(3);
  });
  it('no raw baselines → null avg, 0 saved (honest, not a fake headline)', () => {
    const k = computeKpis([pt(1, { used_tokens: 100 })]);
    expect(k.avgReductionPct).toBeNull();
    expect(k.tokensSaved).toBe(0);
  });
});

describe('filterTurns', () => {
  const points = [
    pt(1, { status_flags: ['gated', 'wire'] }, 'lookup Lam Uyen'),
    pt(2, { status_flags: ['included'] }, 'who are the enemies'),
    pt(3, { status_flags: ['compacted', 'gated'] }, 'darker tone'),
  ];
  it('status filter keeps only turns carrying the flag', () => {
    expect(filterTurns(points, 'gated', '').map((p) => p.sequence_num)).toEqual([1, 3]);
    expect(filterTurns(points, 'compacted', '').map((p) => p.sequence_num)).toEqual([3]);
  });
  it('all keeps everything', () => {
    expect(filterTurns(points, 'all', '')).toHaveLength(3);
  });
  it('query matches the user message (case-insensitive)', () => {
    expect(filterTurns(points, 'all', 'ENEMIES').map((p) => p.sequence_num)).toEqual([2]);
  });
  it('query matches the intent too', () => {
    const withIntent = [pt(9, { status_flags: [], intent: 'tone-edit' }, 'x')];
    expect(filterTurns(withIntent, 'all', 'tone')).toHaveLength(1);
  });
});

describe('filterSpans + spanDeltaKind', () => {
  const spans: TraceSpanFrame[] = [
    { phase: 'planner', tier: 'T5', category: 'grounding', action: 'gate', delta: 0, is_error: false },
    { phase: 'compiler', tier: 'T6', category: 'history', action: 'compact', delta: -5000, is_error: false },
    { phase: 'compiler', tier: 'T1', category: 'results', action: 'reject', delta: 0, is_error: true },
    { phase: 'planner', tier: 'T5', category: 'grounding', action: 'include', delta: 3000, is_error: false },
  ];
  it('planner filter keeps only planner spans', () => {
    expect(filterSpans(spans, 'planner')).toHaveLength(2);
  });
  it('saved filter keeps only negative-delta spans', () => {
    expect(filterSpans(spans, 'saved')).toEqual([spans[1]]);
  });
  it('delta kind: saved / included / reject / neutral', () => {
    expect(spanDeltaKind(spans[0])).toBe('neutral');
    expect(spanDeltaKind(spans[1])).toBe('saved');
    expect(spanDeltaKind(spans[2])).toBe('reject');
    expect(spanDeltaKind(spans[3])).toBe('included');
  });
});

describe('helpers', () => {
  it('turnReductionPct scales the 0–1 frame value to 0–100 (null passthrough)', () => {
    expect(turnReductionPct({ used_tokens: 1, context_length: null, effective_limit: null, pct: null, reduction_pct: 0.43 })).toBe(43);
    expect(turnReductionPct({ used_tokens: 1, context_length: null, effective_limit: null, pct: null })).toBeNull();
  });
  it('statusMeta falls back to the raw flag for an unknown flag', () => {
    expect(statusMeta('made-up').label).toBe('made-up');
    expect(statusMeta('gated').label).toBe('grounding gated');
  });
  it('kfmt compacts thousands', () => {
    expect(kfmt(950)).toBe('950');
    expect(kfmt(1500)).toBe('1.5K');
    expect(kfmt(21300)).toBe('21K');
  });
});
