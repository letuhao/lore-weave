// C28 (dị bản M6) — living-world timeline-tree MODEL builder (pure).
//
// A world surfaces its canon Work as the TRUNK and each dị bản (derivative) Work
// as a BRANCH off the trunk at its chapter-level `branch_point` (G3). The branch
// spine is C23's `source_work_id` self-ref: a derivative Work points at the
// SOURCE Work's surrogate `id`; chaining `source_work_id → id` resolves
// arbitrary-degree derivatives (a derivative of a derivative is a 2nd-degree
// branch). Trunks are Works with NO `source_work_id` (canon).
//
// Branches resolve ONLY among the Works of THIS world's books (the caller passes
// the works it collected per the world's `GET /worlds/{id}/books`), so another
// world's branches can never bleed in — there is no cross-world join here, by
// construction. A derivative whose source is outside the collected set is kept as
// a top-level node flagged `orphanSource` (its parent is unreachable in this
// world) rather than silently dropped.
//
// Pure (no React, no fetch) so the hook + the tests share one source of truth.
import type { Work } from '@/features/composition/types';

/** A node in the living-world tree — one composition Work. */
export interface WorldTreeNode {
  /** The Work's surrogate id (C16/C23) — the branch-spine key. Falls back to
   *  project_id for a pre-C16 row that has no surrogate id. */
  id: string;
  /** The Work itself (carries project_id, book_id, source_work_id, branch_point). */
  work: Work;
  /** The book this Work belongs to (canon + its derivatives share a book_id — COW
   *  makes no book clone), used for navigation + the node label. */
  bookId: string;
  /** The book's display title (from the world's book list). */
  bookTitle: string;
  /** true = canon trunk (no source_work_id); false = a dị bản branch. */
  isCanon: boolean;
  /** The chapter-level branch_point this derivative diverges at (G3). null for a
   *  trunk / a derivative with no recorded branch_point. */
  branchPoint: number | null;
  /** The parent node id (the source Work) — null for a trunk or an orphan. */
  parentId: string | null;
  /** Depth in the tree: 0 = trunk, 1 = 1st-degree branch, 2 = 2nd-degree, … */
  depth: number;
  /** true when this is a derivative whose source Work is NOT among the world's
   *  collected Works (parent unreachable here). Rendered at the root so it is
   *  never silently hidden. */
  orphanSource: boolean;
}

/** One edge connecting a branch to its source (parent → child). */
export interface WorldTreeEdge {
  id: string;
  /** Source (parent) node id. */
  from: string;
  /** Derivative (child) node id. */
  to: string;
  /** The branch_point the child diverges at (for the connector label). */
  branchPoint: number | null;
}

export interface WorldTreeModel {
  nodes: WorldTreeNode[];
  edges: WorldTreeEdge[];
  /** Count of trunk (canon) nodes. */
  trunkCount: number;
  /** Count of branch (derivative) nodes. */
  branchCount: number;
}

/** The minimal book shape the builder needs (id + title), from the world's
 *  `GET /worlds/{id}/books`. */
export interface WorldBookRef {
  bookId: string;
  title: string;
}

/** The surrogate-id key of a Work (the branch-spine identity). Prefer `id`
 *  (C16/C23 surrogate PK); fall back to project_id for a legacy row. */
function workKey(w: Work): string | null {
  return w.id ?? w.project_id ?? null;
}

/**
 * Build the living-world tree from the world's books + the Works collected for
 * those books. `worksByBook` maps a bookId → its Works (canon + derivatives;
 * COW keeps derivatives on the source's book_id). Branch parentage is resolved
 * by `source_work_id → id` ACROSS all collected Works (a derivative may live on
 * the same book as its source, but the chain is global to the world).
 */
export function buildWorldTree(
  books: WorldBookRef[],
  worksByBook: Record<string, Work[]>,
): WorldTreeModel {
  const titleOf = new Map(books.map((b) => [b.bookId, b.title]));

  // Flatten every Work in the world (de-duplicated by surrogate key — a Work is
  // listed once even if a resolution returns it as both `work` and a candidate).
  const flat = new Map<string, { work: Work; bookId: string }>();
  for (const b of books) {
    for (const w of worksByBook[b.bookId] ?? []) {
      const key = workKey(w);
      if (!key) continue; // a lazy null-project pending Work has no spine identity
      if (!flat.has(key)) flat.set(key, { work: w, bookId: b.bookId });
    }
  }

  const present = new Set(flat.keys());

  // First pass: build raw nodes (depth/parent resolved in the second pass).
  const nodes = new Map<string, WorldTreeNode>();
  for (const [key, { work, bookId }] of flat) {
    const src = work.source_work_id ?? null;
    const isCanon = !src;
    const orphanSource = !!src && !present.has(src);
    nodes.set(key, {
      id: key,
      work,
      bookId,
      bookTitle: titleOf.get(bookId) ?? bookId,
      isCanon,
      branchPoint: work.branch_point ?? null,
      // A node whose source is unreachable in this world is rooted (parentId null)
      // so the tree still renders it; orphanSource flags why.
      parentId: isCanon || orphanSource ? null : src,
      depth: 0,
      orphanSource,
    });
  }

  // Second pass: compute depth by walking parent links (cycle-safe via a visited
  // guard — a self-referential / cyclic chain stops at the first repeat).
  const depthOf = (key: string): number => {
    let depth = 0;
    let cur = nodes.get(key)?.parentId ?? null;
    const seen = new Set<string>([key]);
    while (cur && !seen.has(cur) && nodes.has(cur)) {
      seen.add(cur);
      depth += 1;
      cur = nodes.get(cur)?.parentId ?? null;
    }
    return depth;
  };
  for (const node of nodes.values()) node.depth = depthOf(node.id);

  // Edges: one per branch (a node with a resolvable parent in this world).
  const edges: WorldTreeEdge[] = [];
  for (const node of nodes.values()) {
    if (node.parentId && nodes.has(node.parentId)) {
      edges.push({
        id: `${node.parentId}->${node.id}`,
        from: node.parentId,
        to: node.id,
        branchPoint: node.branchPoint,
      });
    }
  }

  // Stable order: trunks first, then branches by depth then book title — a
  // deterministic layout seed (no server layout).
  const ordered = [...nodes.values()].sort((a, b) => {
    if (a.depth !== b.depth) return a.depth - b.depth;
    if (a.isCanon !== b.isCanon) return a.isCanon ? -1 : 1;
    return a.bookTitle.localeCompare(b.bookTitle) || a.id.localeCompare(b.id);
  });

  return {
    nodes: ordered,
    edges,
    trunkCount: ordered.filter((n) => n.isCanon).length,
    branchCount: ordered.filter((n) => !n.isCanon).length,
  };
}

/** Layout the tree onto SVG positions for GraphCanvas (reused, no new lib).
 *  Trunk(s) sit in a left column; each branch is placed to the right of its
 *  parent, stacked vertically by branch index — a simple deterministic tree
 *  layout (hand-rolled, like radialLayout). Pure + exported for tests. */
export interface TreeLayoutPos { x: number; y: number }

const COL_GAP = 220; // horizontal gap per depth level
const ROW_GAP = 84; // vertical gap per sibling
const PAD = 24;

export function layoutWorldTree(model: WorldTreeModel): Record<string, TreeLayoutPos> {
  const out: Record<string, TreeLayoutPos> = {};
  // Children grouped by parent (null parent = a root: trunk or orphan).
  const childrenOf = new Map<string | null, WorldTreeNode[]>();
  for (const n of model.nodes) {
    const k = n.parentId;
    if (!childrenOf.has(k)) childrenOf.set(k, []);
    childrenOf.get(k)!.push(n);
  }

  let row = 0;
  // Pre-order DFS: EVERY node (root, internal, or leaf) occupies its own row
  // band, so subtrees never overlap — including the multi-trunk case (two canon
  // books in one world share depth 0 but get distinct rows). x is set by depth;
  // y by the running row counter, advanced once per placed node.
  const place = (node: WorldTreeNode): void => {
    out[node.id] = { x: PAD + node.depth * COL_GAP, y: PAD + row * ROW_GAP };
    row += 1;
    for (const k of childrenOf.get(node.id) ?? []) place(k);
  };
  const roots = childrenOf.get(null) ?? [];
  for (const r of roots) place(r);

  return out;
}
