// LOOM Composition (T1.3) — pure auto-layout for the Scene Graph. Scenes are laid
// out in columns by their reading axis (`story_order`): each distinct story_order
// is a column (left→right = earlier→later in the read), scenes sharing one stack
// in rows. Scenes with no story_order (un-renumbered) fall into a trailing column.
// Deterministic (sorted by story_order, then rank, then id) so the graph is stable
// across renders; the author's drag overrides any seed (SceneGraphCanvas merges
// `local ?? auto`). Exported constants keep node/edge geometry in one place.
import type { OutlineNode } from '../types';

export const NODE_W = 148;
export const NODE_H = 56;
export const COL_W = 200;
export const ROW_H = 84;
export const PAD = 24;

export type Pos = { x: number; y: number };

// story_order is the column key; null sorts AFTER all real orders (a trailing
// "unplaced" column) — Number.POSITIVE_INFINITY as the sentinel.
function colKey(n: OutlineNode): number {
  return n.story_order ?? Number.POSITIVE_INFINITY;
}

export function autoLayout(scenes: OutlineNode[]): Record<string, Pos> {
  // Stable order: by column (story_order), then rank, then id — so rows within a
  // column are deterministic regardless of input order.
  const sorted = [...scenes].sort(
    (a, b) => colKey(a) - colKey(b) || (a.rank < b.rank ? -1 : a.rank > b.rank ? 1 : 0) || (a.id < b.id ? -1 : 1),
  );
  const columns: number[] = []; // distinct colKeys in encounter order (already sorted)
  const rowOf = new Map<number, number>(); // colKey → next free row
  const out: Record<string, Pos> = {};
  for (const n of sorted) {
    const key = colKey(n);
    let col = columns.indexOf(key);
    if (col === -1) {
      col = columns.length;
      columns.push(key);
    }
    const row = rowOf.get(key) ?? 0;
    rowOf.set(key, row + 1);
    out[n.id] = { x: PAD + col * COL_W, y: PAD + row * ROW_H };
  }
  return out;
}
