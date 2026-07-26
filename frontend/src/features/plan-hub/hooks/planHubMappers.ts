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
    written: n.written,
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

/**
 * PH12 (as amended by SC11) — the union state, now a PROJECTION of a server-maintained fact.
 *
 * WHAT USED TO BE HERE, and why it is gone. This was a client-side two-truths join: it paged
 * book-service's scene index per chapter, matched `scenes.source_scene_id` against spec-node ids,
 * and — the hard part — refused to call a node "planned-only" until ITS OWN chapter's scenes were
 * FULLY read, because absence is only evidence against a set you have finished reading. Judging
 * early is the `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent` bug, and it
 * would paint a finished book as unwritten. That guard was correct, and it took a HIGH-severity fix
 * to get right. It needed a generation guard, a fetch-dedupe set, a page-walk bound and an error
 * channel to stay correct — ~130 lines (`useActualState`), all of which existed only because the
 * derivation lived where data arrives incrementally, out of order, and can be interrupted.
 *
 * None of that is needed now. `written` is MAINTAINED on write (`outline_node.written_scene_id`,
 * reconciled from `scenes.source_scene_id` — the fact book-service already knows when it writes the
 * link). The partial-read bug class is STRUCTURALLY IMPOSSIBLE here: the reconcile is atomic against
 * a full read that RAISES rather than returning a partial one, so the client never sees a
 * half-answer to mis-judge. And the fact is finally reachable by an agent, instead of dying with the
 * panel.
 *
 * 'imported-unplanned' is still NOT emitted here — it cannot be: this map is keyed by SPEC-node id,
 * and a manuscript unit with no spec node has none. It is the PH21 tray, riding
 * `overlay.unplanned_chapters` (the shared server-side coverage diff, 28 OQ-4).
 */
export function computeUnionState(
  /** Each loaded spec SCENE node, carrying the SERVER's written verdict. */
  sceneNodes: Iterable<{ id: string; written: boolean }>,
): Record<string, NodeUnionState> {
  const out: Record<string, NodeUnionState> = {};
  for (const n of sceneNodes) out[n.id] = n.written ? 'written' : 'planned-only';
  return out;
}
