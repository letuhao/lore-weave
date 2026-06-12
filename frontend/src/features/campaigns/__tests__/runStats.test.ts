import { describe, it, expect } from 'vitest';
import { deriveRunStats } from '../runStats';

const START = '2026-06-10T00:00:00Z';

describe('deriveRunStats (G3)', () => {
  it('computes elapsed, throughput and ETA from total stage-completions', () => {
    // started 1h ago, 60 of 240 stage-units settled → 1.0/min; remaining 180 → ETA 3h.
    // (review-impl: rate is over ALL stage-completions, so a phase_barrier run shows
    //  a live ETA during the knowledge phase, not "—".)
    const now = Date.parse('2026-06-10T01:00:00Z');
    const s = deriveRunStats({
      startedAt: START, finishedAt: null, terminal: false,
      totalUnits: 240, doneUnits: 60, inProgress: 8, nowMs: now,
    });
    expect(s.elapsed).toBe('1h00m');
    expect(s.throughput).toBe('1.0/min');
    expect(s.eta).toBe('3h00m');
    expect(s.inProgress).toBe(8);
  });

  it('rate is non-zero during the knowledge phase (phase_barrier, translation=0)', () => {
    // 1h elapsed, knowledge progressing (120 of 480 units) but ZERO translation yet.
    const now = Date.parse('2026-06-10T01:00:00Z');
    const s = deriveRunStats({
      startedAt: START, finishedAt: null, terminal: false,
      totalUnits: 480, doneUnits: 120, inProgress: 8, nowMs: now,
    });
    expect(s.throughput).toBe('2.0/min');  // would be "—" under the old translation-only metric
    expect(s.eta).toBe('3h00m');           // remaining 360 / 2.0/min
  });

  it('no ETA once terminal (uses finished_at for elapsed)', () => {
    const s = deriveRunStats({
      startedAt: START, finishedAt: '2026-06-10T02:30:00Z', terminal: true,
      totalUnits: 100, doneUnits: 100, inProgress: 0, nowMs: Date.parse('2026-06-10T09:00:00Z'),
    });
    expect(s.elapsed).toBe('2h30m');   // finished-started, not now
    expect(s.eta).toBe('—');
  });

  it('dashes when never started', () => {
    const s = deriveRunStats({
      startedAt: null, finishedAt: null, terminal: false,
      totalUnits: 10, doneUnits: 0, inProgress: 0, nowMs: Date.now(),
    });
    expect(s).toMatchObject({ elapsed: '—', throughput: '—', eta: '—' });
  });

  it('no ETA when nothing settled yet (zero throughput)', () => {
    const now = Date.parse('2026-06-10T00:10:00Z');
    const s = deriveRunStats({
      startedAt: START, finishedAt: null, terminal: false,
      totalUnits: 50, doneUnits: 0, inProgress: 4, nowMs: now,
    });
    expect(s.throughput).toBe('—');
    expect(s.eta).toBe('—');
    expect(s.elapsed).toBe('10m');
  });
});
