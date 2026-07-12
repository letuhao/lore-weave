// Plan Hub v2 (spec 24 §H2) — the PURE projection functions the slice hooks share.
// Kept out of the hook files so they carry no React/react-query import and can be unit
// tested directly (the "map to laneLayout inputs" + "two-truths join" contracts, PH11/PH12).
// laneLayout is the ONE "where does a node go" — these only RESHAPE read-surface rows into
// its input types; they never compute a position.
import type {
  ArcListNode,
  ArcShellNode,
  NodeUnionState,
  SummaryNode,
  WindowNode,
} from '../types';
import type { Scene } from '@/features/books/api';
import type { ActualScene } from '../types';

/**
 * Read surface #2 row → laneLayout WindowNode. `story_order` is coerced null→0 because
 * laneLayout's WindowNode.story_order is a plain `number` (a null-order chapter sorts to the
 * front deterministically rather than crashing the x-axis sort). All other fields pass through.
 */
export function toWindowNode(n: SummaryNode): WindowNode {
  return {
    id: n.id,
    kind: n.kind,
    parent_id: n.parent_id,
    structure_node_id: n.structure_node_id,
    chapter_id: n.chapter_id,
    // Pass the position through UNCHANGED, including null. Coercing null→0 here claimed every
    // unordered chapter was the book's FIRST — and since chapter story_order was NEVER written
    // (the bug this fixes), that meant EVERY chapter tied at 0 and the canvas x-axis silently
    // degraded to the id tiebreak. laneLayout sorts a null LAST (absent ≠ zero).
    story_order: n.story_order,
    rank: n.rank,
  };
}

/**
 * Read surface #1 row → laneLayout ArcShellNode. ArcListNode.kind is a strict subset
 * ('saga' | 'arc') of StructureKind; a depth-2 node arrives as kind 'arc' and laneLayout
 * derives its leaf/sub-band role from the tree, not from `kind`. The drawer-only extra fields
 * (goal/status/template/…) are dropped here — the canvas + laneLayout read only this subset.
 */
export function toArcShellNode(n: ArcListNode): ArcShellNode {
  return {
    id: n.id,
    kind: n.kind,
    parent_id: n.parent_id,
    rank: n.rank,
    title: n.title,
    span: n.span,                                  // display ordinal ("chapters 1–3")
    first_story_order: n.first_story_order ?? null, // raw sort key (the chapter cards' axis)
    is_contiguous: n.is_contiguous,
    chapter_count: n.chapter_count,
  };
}

/** book-service Scene (identity truth) → the minimal ActualScene the two-truths join needs. */
export function toActualScene(s: Scene): ActualScene {
  return {
    scene_id: s.scene_id,
    chapter_id: s.chapter_id,
    source_scene_id: s.source_scene_id,
    index: s.sort_order,
  };
}

/**
 * PH12 — the two-truths join, keyed by SPEC scene-node id.
 *   • a spec scene node with a matching manuscript scene (its id ∈ writtenNodeIds) → 'written'
 *   • a spec scene node with none → 'planned-only', BUT ONLY once ITS OWN CHAPTER's manuscript scenes
 *     are fully read. Absence is only evidence against a set you have finished reading; while that
 *     chapter is still paging (or its read FAILED), such a node gets NO entry and renders neutrally.
 *     Declaring it "planned-only" early is the
 *     `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent` bug — and it would paint a
 *     finished book as unwritten.
 *   • 'imported-unplanned' (a MANUSCRIPT unit with no spec node) is NOT emitted here — it cannot be:
 *     this map is keyed by spec-node id, and such a unit has no spec node. It is the PH21 tray, and
 *     it rides `overlay.unplanned_chapters` (the shared server-side coverage diff, 28 OQ-4).
 *     NOT `laneLayout.unassigned` — that is the opposite set (spec chapters with no ARC).
 * Absent from the map ⇒ unknown/neutral, never a false verdict (absent ≠ written, absent ≠ planned).
 *
 * The completeness gate is PER CHAPTER because the manuscript read is now per chapter (H8.1's budget
 * — the whole-book scene index is not fetched at cold open). A scene whose chapter is loaded can be
 * judged even while OTHER chapters are still arriving.
 */
export function computeUnionState(
  /** Each loaded spec SCENE node: its id + the BOOK chapter it belongs to (`chapter_id`). */
  sceneNodes: Iterable<{ id: string; chapterId: string | null }>,
  writtenNodeIds: Set<string>,
  completeChapters: Set<string>,
): Record<string, NodeUnionState> {
  const out: Record<string, NodeUnionState> = {};
  for (const n of sceneNodes) {
    if (writtenNodeIds.has(n.id)) {
      out[n.id] = 'written';
      continue;
    }
    // No manuscript scene points here. That only MEANS something once we've read the whole chapter.
    if (n.chapterId && completeChapters.has(n.chapterId)) out[n.id] = 'planned-only';
    // else: unknown — leave unmapped.
  }
  return out;
}
