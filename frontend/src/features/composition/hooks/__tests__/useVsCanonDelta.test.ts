import { describe, expect, it } from 'vitest';
import { vsCanonDeltas, deltaGlyph } from '../useVsCanonDelta';
import type { Critic } from '../../types';

const mk = (c: number | null, v: number | null, p: number | null, k: number | null): Critic => ({
  coherence: c, voice_match: v, pacing: p, canon_consistency: k, violations: [],
});

describe('vsCanonDeltas (M4 — take − canon, per dim)', () => {
  it('computes a signed per-dim delta against the canon baseline', () => {
    const d = vsCanonDeltas(mk(4, 3, 5, 2), mk(3, 3, 2, 4));
    expect(d.map((x) => x.delta)).toEqual([1, 0, 3, -2]); // C V P K
    expect(d.map((x) => x.take)).toEqual([4, 3, 5, 2]);
    expect(d.map((x) => x.canon)).toEqual([3, 3, 2, 4]);
  });

  it('canon=null (no baseline / unjudged) → every delta is null, take preserved', () => {
    const d = vsCanonDeltas(mk(4, 3, 5, 2), null);
    expect(d.every((x) => x.delta === null)).toBe(true);
    expect(d.map((x) => x.take)).toEqual([4, 3, 5, 2]);
  });

  it('a null dim on EITHER side → that dim delta null-guards (degrade)', () => {
    const d = vsCanonDeltas(mk(4, null, 5, 2), mk(3, 3, null, 4));
    expect(d.map((x) => x.delta)).toEqual([1, null, null, -2]);
  });
});

describe('deltaGlyph', () => {
  it('maps sign to ▲ / ▼ / = and null → –', () => {
    expect(deltaGlyph(2)).toBe('▲');
    expect(deltaGlyph(-1)).toBe('▼');
    expect(deltaGlyph(0)).toBe('=');
    expect(deltaGlyph(null)).toBe('–');
  });
});
