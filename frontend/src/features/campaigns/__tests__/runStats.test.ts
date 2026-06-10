import { describe, it, expect } from 'vitest';
import { deriveRunStats } from '../runStats';

const START = '2026-06-10T00:00:00Z';

describe('deriveRunStats (G3)', () => {
  it('computes elapsed, throughput and ETA for a running campaign', () => {
    // started 1h ago, 60 of 240 translated → 60 ch/h = 1 ch/min; remaining 180 → ETA 180m=3h
    const now = Date.parse('2026-06-10T01:00:00Z');
    const s = deriveRunStats({
      startedAt: START, finishedAt: null, terminal: false,
      total: 240, translationDone: 60, inProgress: 8, nowMs: now,
    });
    expect(s.elapsed).toBe('1h00m');
    expect(s.throughput).toBe('1.0 ch/min');
    expect(s.eta).toBe('3h00m');
    expect(s.inProgress).toBe(8);
  });

  it('no ETA once terminal (uses finished_at for elapsed)', () => {
    const s = deriveRunStats({
      startedAt: START, finishedAt: '2026-06-10T02:30:00Z', terminal: true,
      total: 100, translationDone: 100, inProgress: 0, nowMs: Date.parse('2026-06-10T09:00:00Z'),
    });
    expect(s.elapsed).toBe('2h30m');   // finished-started, not now
    expect(s.eta).toBe('—');
  });

  it('dashes when never started', () => {
    const s = deriveRunStats({
      startedAt: null, finishedAt: null, terminal: false,
      total: 10, translationDone: 0, inProgress: 0, nowMs: Date.now(),
    });
    expect(s).toMatchObject({ elapsed: '—', throughput: '—', eta: '—' });
  });

  it('no ETA when throughput is zero (nothing done yet)', () => {
    const now = Date.parse('2026-06-10T00:10:00Z');
    const s = deriveRunStats({
      startedAt: START, finishedAt: null, terminal: false,
      total: 50, translationDone: 0, inProgress: 4, nowMs: now,
    });
    expect(s.throughput).toBe('—');
    expect(s.eta).toBe('—');
    expect(s.elapsed).toBe('10m');
  });
});
