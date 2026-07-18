// Wave-4 (D-MOTIF-GRAPH-CANVAS) — a bespoke LAYERED DAG auto-layout for the initial (un-dragged)
// motif graph. The edges are acyclic by construction (the motif_link_guard forbids cycles on
// precedes/composed_of), so a longest-path layering (Kahn) gives clean left→right columns without
// a dagre/elk dependency. A node the user has since dragged uses its stored position instead
// (posOf = stored ?? auto ?? default); this only seeds the un-positioned ones.
import type { MotifGraphEdge, MotifGraphNode } from './api';

const COL_W = 220;
const ROW_H = 92;
const PAD = 24;

export type XY = { x: number; y: number };

/** Deterministic layered positions keyed by motif id. Directed edges (from→to) push the target one
 * column right of the deepest source; unconnected nodes land in column 0. Stable for a stable input
 * order, so the layout doesn't jump between loads. */
export function autoLayout(nodes: MotifGraphNode[], edges: MotifGraphEdge[]): Record<string, XY> {
  const ids = nodes.map((n) => n.id);
  const idset = new Set(ids);
  const adj = new Map<string, string[]>();
  const indeg = new Map<string, number>();
  for (const id of ids) { adj.set(id, []); indeg.set(id, 0); }
  for (const e of edges) {
    if (!idset.has(e.from_motif_id) || !idset.has(e.to_motif_id)) continue;
    adj.get(e.from_motif_id)!.push(e.to_motif_id);
    indeg.set(e.to_motif_id, (indeg.get(e.to_motif_id) ?? 0) + 1);
  }

  // Kahn's — layer(v) = max(layer(pred) + 1). Roots (indeg 0) start at column 0.
  const layer = new Map<string, number>();
  const remaining = new Map(indeg);
  const queue = ids.filter((id) => (indeg.get(id) ?? 0) === 0);
  for (const id of queue) layer.set(id, 0);
  const work = [...queue];
  while (work.length) {
    const u = work.shift()!;
    for (const v of adj.get(u)!) {
      layer.set(v, Math.max(layer.get(v) ?? 0, (layer.get(u) ?? 0) + 1));
      const left = (remaining.get(v) ?? 0) - 1;
      remaining.set(v, left);
      if (left === 0) work.push(v);
    }
  }
  // Any node not laid out (defensive — a cycle would leave one, though the guard prevents it) → col 0.
  for (const id of ids) if (!layer.has(id)) layer.set(id, 0);

  const byLayer = new Map<number, string[]>();
  for (const id of ids) {
    const L = layer.get(id)!;
    (byLayer.get(L) ?? byLayer.set(L, []).get(L)!).push(id);
  }
  const pos: Record<string, XY> = {};
  for (const [L, group] of byLayer) {
    group.forEach((id, i) => { pos[id] = { x: PAD + L * COL_W, y: PAD + i * ROW_H }; });
  }
  return pos;
}
