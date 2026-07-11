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
  it('coerces a null story_order to 0 (laneLayout WindowNode.story_order is non-null)', () => {
    const w = toWindowNode(summary({ id: 'ch', kind: 'chapter', story_order: null, structure_node_id: 'A1' }));
    expect(w.story_order).toBe(0);
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
      span: { from_order: 3, to_order: 9 }, is_contiguous: false, chapter_count: 6,
      goal: 'drawer-only', status: 'active',
    }));
    expect(s).toEqual({
      id: 'A1', kind: 'arc', parent_id: 'S', rank: 'c', title: 'Rising',
      span: { from_order: 3, to_order: 9 }, is_contiguous: false, chapter_count: 6,
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
  it("marks a spec node 'written' when a manuscript scene points at it", () => {
    const u = computeUnionState(['n1', 'n2'], new Set(['n1']), true);
    expect(u.n1).toBe('written');
  });
  it("marks an unmatched spec node 'planned-only' — but only once the index is complete", () => {
    expect(computeUnionState(['n2'], new Set(['n1']), true).n2).toBe('planned-only');
  });
  it('leaves an unmatched spec node UNMAPPED while the manuscript index is still loading (absent ≠ planned)', () => {
    const u = computeUnionState(['n2'], new Set(['n1']), false);
    expect('n2' in u).toBe(false);
  });
  it("still resolves 'written' even while incomplete (a positive match is safe pre-completion)", () => {
    expect(computeUnionState(['n1'], new Set(['n1']), false).n1).toBe('written');
  });
  it('never emits imported-unplanned (that is laneLayout.unplanned, not this map)', () => {
    const u = computeUnionState(['n1', 'n2'], new Set(['n1']), true);
    expect(Object.values(u)).not.toContain('imported-unplanned');
  });
  it('an empty spec set yields an empty map', () => {
    expect(computeUnionState([], new Set(['n1']), true)).toEqual({});
  });
});
