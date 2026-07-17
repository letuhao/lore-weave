// Plan Hub redesign (2026-07-18) — the LANE-FLOW tree projection.
//
// The sealed Advanced mockup (`design-drafts/plan-hub-redesign/index.html`) is a CSS-FLOW layout:
// arcs are vertically-stacked bordered lanes; a lane's chapters WRAP into rows inside it; scenes are
// chips under a chapter; a sub-arc is an inset lane. That is a document tree, not a graph — so it does
// NOT consume `laneLayout`'s absolute x/y positions (those drive the React Flow canvas). It needs the
// arc → chapter → scene TREE, which this pure function builds from the same two read surfaces the Hub
// already loads (the arc shell + the keyset windows). Pure + headless ⇒ unit-testable without React.
//
// Windowing is UNCHANGED (mockup "scale" note): a COLLAPSED arc contributes no chapters here (the hook
// never loaded them); a chapter's scenes appear only when the chapter is expanded. This tree is a
// projection of whatever is loaded — it never fetches.
import type { ArcListNode, NodeSource, SummaryNode } from '../types';

export interface LaneScene {
  id: string;
  title: string;
  status: string;
  source: NodeSource;
  written: boolean;
  storyOrder: number | null;
}

export interface LaneChapter {
  /** outline_node id (the spec node). */
  id: string;
  /** book-service chapter_id (needed to add a scene / open the editor). null ⇒ not yet known. */
  chapterId: string | null;
  storyOrder: number | null;
  title: string;
  status: string;
  source: NodeSource;
  written: boolean;
  scenes: LaneScene[];
  /** The chapter's scene branch is open (scenes loaded/shown). */
  scenesExpanded: boolean;
}

export interface LaneArc {
  /** structure_node id. */
  id: string;
  kind: 'saga' | 'arc';
  /** Nesting depth recomputed from the tree (0 = root); a sub-arc is depth ≥ 1. */
  depth: number;
  title: string;
  status: string;
  source: NodeSource;
  /** BA6 reading-position span ("chapters 1–4"), or null when the arc holds no chapters. */
  span: { from_order: number; to_order: number } | null;
  /** A short human description (arc.summary), or null. */
  summary: string | null;
  isContiguous: boolean;
  chapterCount: number;
  /** The lane is collapsed to a header-only rollup (no chapters shown / loaded). */
  collapsed: boolean;
  /** Directly-bound chapters (loaded window), in reading order. Empty when collapsed. */
  chapters: LaneChapter[];
  /** Nested sub-arcs (recursive), in sibling rank order. */
  subArcs: LaneArc[];
}

/** Story-order sort key: an unknown position sorts LAST (mirrors the server's NULLS LAST). */
function orderKey(o: number | null): number {
  return o ?? Number.POSITIVE_INFINITY;
}

/** (rank, id) order — the same the keyset windows page by. */
function byRank<T extends { rank: string; id: string }>(a: T, b: T): number {
  if (a.rank < b.rank) return -1;
  if (a.rank > b.rank) return 1;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

function push<K, V>(m: Map<K, V[]>, k: K, v: V): void {
  const arr = m.get(k);
  if (arr) arr.push(v);
  else m.set(k, [v]);
}

const src = (s: NodeSource | undefined): NodeSource => (s === 'mined' ? 'mined' : 'authored');

/**
 * Build the arc → chapter → scene forest for the lane-flow Advanced view.
 *
 * @param arcs     read surface #1 (the whole structure tree, one call)
 * @param content  the loaded summary rows by node id (read surface #2 windows)
 * @param expandedArcs     arcs the user (or bounded auto-expand) has opened
 * @param expandedChapters chapters whose scene branch is open
 */
export function buildLaneTree(
  arcs: ArcListNode[],
  content: Record<string, SummaryNode>,
  expandedArcs: Set<string>,
  expandedChapters: Set<string>,
): LaneArc[] {
  // Group the loaded windows: chapters under their arc, scenes under their chapter.
  const chaptersByArc = new Map<string, SummaryNode[]>();
  const scenesByChapter = new Map<string, SummaryNode[]>();
  for (const n of Object.values(content)) {
    if (n.kind === 'chapter' && n.structure_node_id) push(chaptersByArc, n.structure_node_id, n);
    else if (n.kind === 'scene' && n.parent_id) push(scenesByChapter, n.parent_id, n);
  }

  const buildScene = (n: SummaryNode): LaneScene => ({
    id: n.id,
    title: n.title,
    status: n.status,
    source: src(n.source),
    written: n.written,
    storyOrder: n.story_order,
  });

  const buildChapter = (n: SummaryNode): LaneChapter => {
    const scenesExpanded = expandedChapters.has(n.id);
    const scenes = scenesExpanded
      ? (scenesByChapter.get(n.id) ?? [])
          .slice()
          .sort((a, b) => orderKey(a.story_order) - orderKey(b.story_order) || byRank(a, b))
          .map(buildScene)
      : [];
    return {
      id: n.id,
      chapterId: n.chapter_id,
      storyOrder: n.story_order,
      title: n.title,
      status: n.status,
      source: src(n.source),
      written: n.written,
      scenes,
      scenesExpanded,
    };
  };

  // The arc forest, by parent_id + rank. A parent_id outside the set is treated as a root
  // (defensive — arc_list is one whole-book call, so this should not happen).
  const byId = new Map(arcs.map((a) => [a.id, a]));
  const childrenOf = new Map<string | null, ArcListNode[]>();
  for (const a of arcs) {
    const key = a.parent_id && byId.has(a.parent_id) ? a.parent_id : null;
    push(childrenOf, key, a);
  }

  const buildArc = (a: ArcListNode, depth: number): LaneArc => {
    const collapsed = !expandedArcs.has(a.id);
    const chapters = collapsed
      ? []
      : (chaptersByArc.get(a.id) ?? [])
          .slice()
          .sort((x, y) => orderKey(x.story_order) - orderKey(y.story_order) || byRank(x, y))
          .map(buildChapter);
    const kids = (childrenOf.get(a.id) ?? []).slice().sort(byRank);
    return {
      id: a.id,
      kind: a.kind,
      depth,
      title: a.title,
      status: a.status,
      source: src(a.source),
      span: a.span,
      summary: a.summary?.trim() ? a.summary.trim() : null,
      isContiguous: a.is_contiguous,
      chapterCount: a.chapter_count,
      collapsed,
      chapters,
      subArcs: kids.map((k) => buildArc(k, depth + 1)),
    };
  };

  return (childrenOf.get(null) ?? []).slice().sort(byRank).map((r) => buildArc(r, 0));
}

/** The first N root-arc ids — the bounded set the flow view auto-expands on open so the hierarchy is
 *  visible by default (mockup "root fix 2") without firing a chapter-window fetch per arc on a
 *  1000-arc book (the documented cold-open budget). Roots only: a sub-arc opens with its parent. */
export function autoExpandArcIds(arcs: ArcListNode[], max: number): string[] {
  const byId = new Map(arcs.map((a) => [a.id, a]));
  return arcs
    .filter((a) => !a.parent_id || !byId.has(a.parent_id))
    .slice()
    .sort(byRank)
    .slice(0, max)
    .map((a) => a.id);
}
