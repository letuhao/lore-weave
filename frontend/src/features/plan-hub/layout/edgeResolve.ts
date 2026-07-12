// 24 PH13 — resolving a scene-link edge onto the CURRENTLY RENDERED node set.
//
// The rule PH13 states: "An edge whose other endpoint is not loaded/collapsed renders as a stub
// connector into the collapsed node, which carries an edge-count badge — never silently dropped."
//
// What actually shipped: the canvas mapped `from_node_id`/`to_node_id` straight to React Flow. When
// an endpoint sat inside a collapsed arc that node did not exist in the node list, and RF discarded
// the edge without a word. The user saw a setup with no payoff and no indication that a payoff
// existed at all — a silent truncation dressed up as an empty graph.
//
// The fix has two halves:
//   • the SERVER now ships each endpoint's ancestry (chapter node + arc), because a collapsed arc
//     never loads its chapters, so the client genuinely cannot know where the endpoint lives;
//   • this pure function walks that ancestry to the nearest node that IS on screen.
//
// Resolution order per endpoint (most specific first):
//     the scene itself → its chapter card → its arc's rollup card → unresolvable
// "Unresolvable" is not "drop it": the caller COUNTS those and says so.
import type { NodePosition, SceneLinkEdge } from '../types';

/** Where an edge endpoint actually landed on screen. */
export interface ResolvedEndpoint {
  /** The rendered node id to attach to. */
  nodeId: string;
  /** True when we attached to an ANCESTOR (chapter card / arc rollup) rather than the node itself —
   *  i.e. this end of the edge is a STUB into something collapsed. */
  stub: boolean;
}

export interface ResolvedEdge {
  edge: SceneLinkEdge;
  source: string;
  target: string;
  /** Either end (or both) attached to an ancestor ⇒ render as a stub connector, styled distinctly. */
  stub: boolean;
}

export interface EdgeResolution {
  edges: ResolvedEdge[];
  /**
   * Edges we could NOT place — both a self-loop after collapse (source === target: the two endpoints
   * folded into the SAME rollup, so an edge would be a meaningless circle) and a genuinely
   * unresolvable endpoint. Counted per rendered node so a rollup can badge "3 links inside".
   */
  hiddenByNode: Record<string, number>;
  /** Edges with no rendered anchor at all — nothing on screen can even carry their badge. */
  unresolvable: number;
}

function resolveEndpoint(
  nodeId: string,
  chapterNodeId: string | null,
  arcId: string | null,
  rendered: Set<string>,
): ResolvedEndpoint | null {
  if (rendered.has(nodeId)) return { nodeId, stub: false };
  // The chapter is on screen but its scene branch is collapsed → stub into the chapter card.
  if (chapterNodeId && rendered.has(chapterNodeId)) return { nodeId: chapterNodeId, stub: true };
  // The whole arc is collapsed → stub into its rollup card (the rollup's id IS the arc's id).
  if (arcId && rendered.has(arcId)) return { nodeId: arcId, stub: true };
  return null;
}

/**
 * Map every edge onto the rendered node set. PURE — the canvas does no graph reasoning of its own.
 *
 * `rendered` must be the ids the canvas will actually hand React Flow (layout.nodes), which includes
 * arc-rollup cards under their ARC id — that is what lets a collapsed arc be a stub target.
 */
export function resolveEdges(edges: SceneLinkEdge[], nodes: NodePosition[]): EdgeResolution {
  const rendered = new Set(nodes.map((n) => n.id));
  const out: ResolvedEdge[] = [];
  const hiddenByNode: Record<string, number> = {};
  let unresolvable = 0;

  const bump = (id: string) => {
    hiddenByNode[id] = (hiddenByNode[id] ?? 0) + 1;
  };

  for (const e of edges) {
    const from = resolveEndpoint(e.from_node_id, e.from_chapter_node_id, e.from_arc_id, rendered);
    const to = resolveEndpoint(e.to_node_id, e.to_chapter_node_id, e.to_arc_id, rendered);

    if (!from || !to) {
      // At least one end has nothing on screen. Badge whichever end we DID resolve, so the count is
      // still visible somewhere; if neither resolved, nothing on the canvas can carry it.
      if (from) bump(from.nodeId);
      else if (to) bump(to.nodeId);
      else unresolvable += 1;
      continue;
    }

    if (from.nodeId === to.nodeId) {
      // Both ends folded into the SAME card (e.g. a setup and its payoff inside one collapsed arc).
      // Drawing a self-loop would be noise; the rollup badges it as an edge living inside it.
      bump(from.nodeId);
      continue;
    }

    out.push({
      edge: e,
      source: from.nodeId,
      target: to.nodeId,
      stub: from.stub || to.stub,
    });
  }

  return { edges: out, hiddenByNode, unresolvable };
}
