// 24 §H2 — the slice hooks' pure projections: SummaryNode→WindowNode / ArcListNode→ArcShellNode
// (the laneLayout inputs, PH11) and the two-truths union join (PH12). Headless, no React.
import { describe, expect, it } from 'vitest';
import { computeUnionState, toActualScene, toArcShellNode, toWindowNode } from '../planHubMappers';
import type { ArcListNode, SummaryNode } from '../../types';
import type { Scene } from '@/features/books/api';

const summary = (o: Partial<SummaryNode> & { id: string; kind: 'chapter' | 'scene' }): SummaryNode => ({
  parent_id: null, structure_node_id: null, chapter_id: null, title: '', status: 'outline',
  version: 1, story_order: 0, rank: 'm', beat_role: null, tension: null, pov_entity_id: null,
  present_entity_ids: [], present_entity_count: 0, ...o,
});
const arcNode = (o: Partial<ArcListNode> & { id: string }): ArcListNode => ({
  kind: 'arc', parent_id: null, depth: 0, rank: 'm', title: o.id, status: 'active', version: 1,
  span: null, is_contiguous: true, chapter_count: 0, ...o,
});
const scene = (o: Partial<Scene> & { scene_id: string }): Scene => ({
  book_id: 'b', chapter_id: 'ch1', sort_order: 0, title: null, path: '/0', leaf_text: '',
  content_hash: 'h', source_scene_id: null, parse_version: 1, lifecycle_state: 'active', ...o,
});

describe('toWindowNode (PH11) — read surface #2 → laneLayout WindowNode', () => {
  it('preserves an UNKNOWN story_order as null — it must never become position 0', () => {
    // This previously coerced null → 0, which asserts "this chapter is the book's FIRST". While
    // chapter story_order was never written at all (the writer omitted it), that tied EVERY chapter
    // at 0 and the canvas x-axis silently fell through to the id tiebreak — it showed no reading
    // order whatsoever. Absent ≠ zero: laneLayout sorts a null LAST and renders it as unordered.
    const w = toWindowNode(summary({ id: 'ch', kind: 'chapter', story_order: null, structure_node_id: 'A1' }));
    expect(w.story_order).toBeNull();
    expect(w.structure_node_id).toBe('A1');
    expect(w.kind).toBe('chapter');
  });
  it('passes through a scene node with its parent (chapter) id and preserves a real order', () => {
    const w = toWindowNode(summary({ id: 'sc', kind: 'scene', parent_id: 'ch', story_order: 7, rank: 'q' }));
    expect(w).toEqual({ id: 'sc', kind: 'scene', parent_id: 'ch', structure_node_id: null, chapter_id: null, story_order: 7, rank: 'q' });
  });
});

describe('toArcShellNode (PH11) — read surface #1 → laneLayout ArcShellNode', () => {
  it('keeps only the shell subset and preserves span/contiguity/count', () => {
    const s = toArcShellNode(arcNode({
      id: 'A1', kind: 'arc', parent_id: 'S', rank: 'c', title: 'Rising',
      span: { from_order: 3, to_order: 9 }, first_story_order: 3000,
      is_contiguous: false, chapter_count: 6,
      goal: 'drawer-only', status: 'active',
    }));
    expect(s).toEqual({
      id: 'A1', kind: 'arc', parent_id: 'S', rank: 'c', title: 'Rising',
      // `span` is the DISPLAY ordinal ("chapters 3–9"); `first_story_order` is the RAW sort key the
      // rollup card is placed by. Two units, two fields — one field for both put a collapsed arc's
      // rollup at the wrong x.
      span: { from_order: 3, to_order: 9 }, first_story_order: 3000,
      is_contiguous: false, chapter_count: 6,
    });
    expect('goal' in s).toBe(false); // drawer-only extras dropped
  });
  it('carries a saga kind through unchanged', () => {
    expect(toArcShellNode(arcNode({ id: 'S', kind: 'saga' })).kind).toBe('saga');
  });
});

describe('toActualScene — book-service Scene → the join-minimal ActualScene', () => {
  it('maps sort_order→index and keeps the join key source_scene_id', () => {
    expect(toActualScene(scene({ scene_id: 's1', chapter_id: 'c9', source_scene_id: 'n1', sort_order: 4 })))
      .toEqual({ scene_id: 's1', chapter_id: 'c9', source_scene_id: 'n1', index: 4 });
  });
});

describe('computeUnionState (PH12) — the two-truths join, keyed by spec scene-node id', () => {
  // Completeness is PER CHAPTER now: the manuscript half loads lazily, chapter by chapter (H8.1's
  // budget), so a scene may be judged as soon as ITS OWN chapter has been fully read.
  const sc = (id: string, chapterId: string | null = 'bc-1') => ({ id, chapterId });

  it("marks a spec node 'written' when a manuscript scene points at it", () => {
    const u = computeUnionState([sc('n1'), sc('n2')], new Set(['n1']), new Set(['bc-1']));
    expect(u.n1).toBe('written');
  });

  it("marks an unmatched spec node 'planned-only' once ITS chapter is fully read", () => {
    const u = computeUnionState([sc('n2')], new Set(['n1']), new Set(['bc-1']));
    expect(u.n2).toBe('planned-only');
  });

  it('leaves it UNMAPPED while its chapter is still loading (absent ≠ planned)', () => {
    // The chapter isn't in completeChapters — absence proves nothing yet.
    const u = computeUnionState([sc('n2')], new Set(['n1']), new Set());
    expect('n2' in u).toBe(false);
  });

  it('judges only the chapters that ARE complete — a sibling chapter still paging stays neutral', () => {
    // THE case the per-chapter gate exists for: bc-1 is read, bc-2 is not. A scene in bc-2 must not
    // be declared unwritten just because a DIFFERENT chapter finished.
    const u = computeUnionState(
      [sc('a', 'bc-1'), sc('b', 'bc-2')],
      new Set(),
      new Set(['bc-1']),
    );
    expect(u.a).toBe('planned-only');
    expect('b' in u).toBe(false);
  });

  it("still resolves 'written' even while incomplete (a positive match is safe pre-completion)", () => {
    expect(computeUnionState([sc('n1')], new Set(['n1']), new Set()).n1).toBe('written');
  });

  it('a scene with no chapter can never be judged planned-only (nothing to complete)', () => {
    const u = computeUnionState([sc('n2', null)], new Set(), new Set(['bc-1']));
    expect('n2' in u).toBe(false);
  });

  it('never emits imported-unplanned (that is the PH21 tray, not this map)', () => {
    const u = computeUnionState([sc('n1'), sc('n2')], new Set(['n1']), new Set(['bc-1']));
    expect(Object.values(u)).not.toContain('imported-unplanned');
  });

  it('an empty spec set yields an empty map', () => {
    expect(computeUnionState([], new Set(['n1']), new Set(['bc-1']))).toEqual({});
  });
});
