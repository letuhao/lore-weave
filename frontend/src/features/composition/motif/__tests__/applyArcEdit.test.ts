// W10 arc-timeline — the PURE edit reducer + layout↔placement mapping. This is the
// brain both the desktop grid and the mobile list drive; if these invariants hold, the
// two surfaces can never diverge. Fully deterministic (no clock/random).
import { describe, expect, it } from 'vitest';
import {
  applyArcEdit, dragEndToMoveEdit, layoutToPlacements, placementsToLayout, threadsToContract,
} from '../applyArcEdit';
import type { ArcPlacement } from '../arcTimelineContract';
import type { ArcLayoutEntry } from '../arcTypes';

const P = (over: Partial<ArcPlacement> = {}): ArcPlacement => ({
  id: 'p0', motif_code: 'duel', motif_id: 'm1', motif_name: 'Duel',
  thread: 'combat', span_start: 2, span_end: 3, ord: 0, ...over,
});

describe('layoutToPlacements / placementsToLayout (mapping)', () => {
  it('synthesizes a stable index id + a name fallback on read', () => {
    const layout: ArcLayoutEntry[] = [
      { motif_code: 'duel', motif_id: 'm1', thread: 'combat', span_start: 2, span_end: 3, ord: 0 },
      { motif_code: '', motif_id: null, thread: 'romance', span_start: 1, span_end: 1, ord: 0 },
    ];
    const ps = layoutToPlacements(layout);
    expect(ps[0].id).toBe('p0');
    expect(ps[1].id).toBe('p1');
    expect(ps[0].motif_name).toBe('duel');   // name falls back to the code
    expect(ps[1].motif_name).toBe('—');       // empty code → em-dash placeholder
  });

  it('strips id + name back to the canonical backend shape and renumbers ord per thread', () => {
    const ps = [
      P({ id: 'p9', thread: 'combat', span_start: 5, span_end: 6, ord: 4 }),
      P({ id: 'p1', thread: 'combat', span_start: 1, span_end: 2, ord: 7 }),
    ];
    const layout = placementsToLayout(ps);
    expect(layout[0]).not.toHaveProperty('id');
    expect(layout[0]).not.toHaveProperty('motif_name');
    // ordered by (thread, span_start) → the earlier-chapter placement is ord 0.
    expect(layout.map((l) => [l.span_start, l.ord])).toEqual([[1, 0], [5, 1]]);
  });

  it('round-trips a layout (read → write preserves the placements)', () => {
    const layout: ArcLayoutEntry[] = [
      { motif_code: 'a', motif_id: null, thread: 't1', span_start: 1, span_end: 2, ord: 0 },
      { motif_code: 'b', motif_id: null, thread: 't1', span_start: 3, span_end: 4, ord: 1 },
    ];
    const back = placementsToLayout(layoutToPlacements(layout));
    expect(back).toEqual(layout);
  });

  it('maps thread label/glyph, falling back label→key', () => {
    expect(threadsToContract([{ key: 'combat', label: '', glyph: '⚔' }])).toEqual([
      { key: 'combat', label: 'combat', glyph: '⚔' },
    ]);
  });
});

describe('applyArcEdit — place', () => {
  it('appends a new placement with a fresh non-colliding id + next ord on the thread', () => {
    const start = [P({ id: 'p0', thread: 'combat', ord: 0 })];
    const next = applyArcEdit(start, { type: 'place', thread: 'combat', motif_code: 'ambush', span_start: 4, span_end: 5 }, 10);
    expect(next).toHaveLength(2);
    expect(next[1]).toMatchObject({ id: 'p1', motif_code: 'ambush', thread: 'combat', span_start: 4, span_end: 5, ord: 1 });
  });

  it('clamps a placed span into [1..chapterSpan] and keeps start ≤ end', () => {
    const next = applyArcEdit([], { type: 'place', thread: 't', motif_code: 'x', span_start: 0, span_end: 99 }, 6);
    expect(next[0]).toMatchObject({ span_start: 1, span_end: 6 });
  });

  it('does not mutate the input array', () => {
    const start = [P()];
    applyArcEdit(start, { type: 'place', thread: 't', motif_code: 'x', span_start: 1, span_end: 1 }, 10);
    expect(start).toHaveLength(1);
  });
});

describe('applyArcEdit — move', () => {
  it('shifts a span width-preserving and changes thread', () => {
    const next = applyArcEdit([P({ id: 'p0', span_start: 2, span_end: 3 })], { type: 'move', placement_id: 'p0', to_thread: 'romance', delta_chapters: 2 }, 10);
    expect(next[0]).toMatchObject({ thread: 'romance', span_start: 4, span_end: 5 });
  });

  it('clamps at the right edge without shrinking the span', () => {
    const next = applyArcEdit([P({ id: 'p0', span_start: 8, span_end: 9 })], { type: 'move', placement_id: 'p0', to_thread: 'combat', delta_chapters: 5 }, 10);
    expect(next[0]).toMatchObject({ span_start: 9, span_end: 10 });  // width 1 preserved
  });

  it('clamps at the left edge to chapter 1', () => {
    const next = applyArcEdit([P({ id: 'p0', span_start: 2, span_end: 4 })], { type: 'move', placement_id: 'p0', to_thread: 'combat', delta_chapters: -9 }, 10);
    expect(next[0]).toMatchObject({ span_start: 1, span_end: 3 });
  });

  it('is a no-op for an unknown placement id', () => {
    const start = [P({ id: 'p0' })];
    const next = applyArcEdit(start, { type: 'move', placement_id: 'ghost', to_thread: 't', delta_chapters: 1 }, 10);
    expect(next).toEqual(start);
  });
});

describe('applyArcEdit — resize', () => {
  it('grows the end edge up to chapterSpan', () => {
    const next = applyArcEdit([P({ id: 'p0', span_start: 2, span_end: 3 })], { type: 'resize', placement_id: 'p0', edge: 'end', delta: 5 }, 6);
    expect(next[0]).toMatchObject({ span_start: 2, span_end: 6 });
  });

  it('shrinking the end never crosses the start (width ≥ 1)', () => {
    const next = applyArcEdit([P({ id: 'p0', span_start: 4, span_end: 5 })], { type: 'resize', placement_id: 'p0', edge: 'end', delta: -9 }, 10);
    expect(next[0]).toMatchObject({ span_start: 4, span_end: 4 });
  });

  it('the start edge never crosses the end and never goes below 1', () => {
    const grow = applyArcEdit([P({ id: 'p0', span_start: 3, span_end: 5 })], { type: 'resize', placement_id: 'p0', edge: 'start', delta: -9 }, 10);
    expect(grow[0]).toMatchObject({ span_start: 1, span_end: 5 });
    const shrink = applyArcEdit([P({ id: 'p0', span_start: 3, span_end: 5 })], { type: 'resize', placement_id: 'p0', edge: 'start', delta: 9 }, 10);
    expect(shrink[0]).toMatchObject({ span_start: 5, span_end: 5 });
  });
});

describe('applyArcEdit — remove', () => {
  it('drops the placement by id', () => {
    const next = applyArcEdit([P({ id: 'p0' }), P({ id: 'p1' })], { type: 'remove', placement_id: 'p0' }, 10);
    expect(next.map((p) => p.id)).toEqual(['p1']);
  });
});

describe('dragEndToMoveEdit (pointer geometry)', () => {
  // 300px track / 10 cols = 30px per chapter.
  const G = { placementId: 'p1', fromThread: 'combat', trackWidth: 300, cols: 10 };

  it('rounds the pixel delta into a chapter delta', () => {
    expect(dragEndToMoveEdit({ ...G, deltaX: 62, overThread: 'combat' }))
      .toEqual({ type: 'move', placement_id: 'p1', to_thread: 'combat', delta_chapters: 2 });
  });

  it('captures a thread change from the row dropped onto, even with no chapter move', () => {
    expect(dragEndToMoveEdit({ ...G, deltaX: 3, overThread: 'romance' }))
      .toEqual({ type: 'move', placement_id: 'p1', to_thread: 'romance', delta_chapters: 0 });
  });

  it('a no-op drag (no chapter delta, same thread) returns null', () => {
    expect(dragEndToMoveEdit({ ...G, deltaX: 4, overThread: 'combat' })).toBeNull();   // 4px < half a chapter
    expect(dragEndToMoveEdit({ ...G, deltaX: 10, overThread: null })).toBeNull();
  });

  it('an unmeasured track (width 0) yields no chapter delta', () => {
    expect(dragEndToMoveEdit({ ...G, trackWidth: 0, deltaX: 999, overThread: 'combat' })).toBeNull();
  });
});
