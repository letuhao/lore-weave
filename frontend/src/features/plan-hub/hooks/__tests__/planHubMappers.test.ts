// 24 §H2 — the slice hooks' pure projections: SummaryNode→WindowNode / ArcListNode→ArcShellNode
// (the laneLayout inputs, PH11) and the two-truths union join (PH12). Headless, no React.
import { describe, expect, it } from 'vitest';
import { computeUnionState, toArcShellNode, toWindowNode } from '../planHubMappers';
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

describe('computeUnionState (PH12, as amended by SC11) — now a PROJECTION of a server fact', () => {
  // ── WHAT THESE TESTS REPLACE, and why they are not simply deleted ─────────────────────────
  //
  // This block used to hold FOUR tests guarding a real, previously-shipped bug class:
  //   `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent`.
  //
  // The old computeUnionState joined spec nodes against book-service's scene index, which the
  // client paged PER CHAPTER. So "no scene points at this node" could mean "not written" OR "that
  // chapter's page hasn't arrived yet" — and calling it 'planned-only' early painted a FINISHED
  // book as unwritten. The guard (a per-chapter completeness set) was correct, and it took a
  // HIGH-severity fix to get right.
  //
  // Deleting those tests without replacing the GUARANTEE is how the bug comes back. So: the
  // guarantee moved to the server, and it is now STRUCTURAL rather than guarded.
  //
  //   * The client never sees a partial answer to mis-judge. `written` is a settled boolean on the
  //     node payload — there is no second, separately-paged source to be half-read.
  //   * The server refuses to produce a verdict from a partial read at all:
  //     `written_verdict_service.fetch_scene_links` RAISES on any non-200 or partial page-walk, and
  //     the reconcile is ONE atomic statement against the FULL set. Proven in
  //     `services/composition-service/tests/integration/db/test_written_verdict.py`:
  //       - test_a_DEGRADED_read_NEVER_clears_the_mirror  ("I could not look" ≠ "there is no prose")
  //       - test_reconcile_sets_the_link_and_is_IDEMPOTENT
  //       - test_reconcile_CLEARS_a_node_whose_scene_is_GONE
  //       - test_a_MOVED_anchor_moves_the_mirror
  //
  // The bug class cannot occur here because the incremental read it needed no longer exists.

  it('projects the server verdict — written', () => {
    expect(computeUnionState([{ id: 's1', written: true }])).toEqual({ s1: 'written' });
  });

  it('projects the server verdict — planned-only', () => {
    expect(computeUnionState([{ id: 's1', written: false }])).toEqual({ s1: 'planned-only' });
  });

  it('a node is NEVER left unmapped — the server always has an answer', () => {
    // The old map deliberately OMITTED a node it could not yet judge (absent ≠ planned), because a
    // half-read set cannot support a verdict. There is no half-read set anymore: every loaded node
    // carries a settled verdict, so a missing entry would now be a BUG, not caution.
    const out = computeUnionState([
      { id: 'a', written: true },
      { id: 'b', written: false },
      { id: 'c', written: false },
    ]);
    expect(Object.keys(out).sort()).toEqual(['a', 'b', 'c']);
  });

  it('never emits imported-unplanned — it cannot, and that is still true', () => {
    // This map is keyed by SPEC-node id; a manuscript unit with no spec node has none. It is the
    // PH21 tray's business, riding overlay.unplanned_chapters (the server-side coverage diff).
    const out = computeUnionState([{ id: 's1', written: true }, { id: 's2', written: false }]);
    expect(Object.values(out)).not.toContain('imported-unplanned');
  });

  it('empty in, empty out', () => {
    expect(computeUnionState([])).toEqual({});
  });
});

