// Manuscript navigator (#02) — source-agnostic tree model.
//
// The tree is fed by TWO sources (see useManuscriptTree): a book with no composition Work
// renders a FLAT chapter list from book-service (cursor-paged); a book WITH a Work renders
// the composition outline as arc → chapter → scene (lazy-paged children). Both produce the
// same ManuscriptNode/Row shapes so the view is one component.

// 'part' = a manuscript act/volume group header (S-02). Rendered like an arc group
// header but backed by a book-service `parts` row, and — unlike an arc — editable
// (rename/trash) + a drop target for moving chapters between acts. Its node id is the
// part_id, or PART_UNASSIGNED_ID for the synthetic "flat manuscript" bucket.
export type ManuscriptRowKind = 'arc' | 'chapter' | 'scene' | 'part';

/** A node in the in-memory manuscript tree. */
export interface ManuscriptNode {
  id: string;                 // stable row id (book chapter id, or outline node id)
  kind: ManuscriptRowKind;
  title: string;
  number: number | null;      // chapter display number (book sort_order); null for arc/scene
  status: string | null;      // outline status (scene/chapter); null otherwise
  chapterId: string | null;   // the BOOK chapter this row opens (arc → null). Dock target.
  hasChildren: boolean;       // can be expanded to lazy-load children
  childCount: number | null;  // sidebar badge: a chapter's scene count / an arc's chapter count. null = unknown (flat chapters).
}

/** A flattened render row. Four kinds:
 *  - `node`      — a real tree node.
 *  - `skeleton`  — a shimmer placeholder while a parent's FIRST page is loading (nothing yet).
 *  - `more`      — a "load next page" affordance for a parent that already has ≥1 page loaded.
 * (`skeleton` and `more` are mutually exclusive per parent — first load shimmers, later pages page.) */
export type ManuscriptRow =
  | { type: 'node'; node: ManuscriptNode; depth: number; expanded: boolean; loading: boolean }
  | { type: 'skeleton'; depth: number; key: string }
  | { type: 'more'; parentKey: string; parentNodeId: string | null; depth: number };

/** childrenOf / childCursor key for the top level (arcs, or flat chapters). */
export const ROOT_KEY = '';

export interface TreeState {
  nodes: Record<string, ManuscriptNode>;
  childrenOf: Record<string, string[]>;         // loaded child ids per parent key
  childCursor: Record<string, string | null>;   // next-page cursor per parent (string = more, null = done, undefined = unloaded)
  expanded: Record<string, boolean>;
  loading: Record<string, boolean>;             // children of this key are being fetched
}

export const emptyTree = (): TreeState => ({
  nodes: {},
  childrenOf: {},
  childCursor: {},
  expanded: {},
  loading: {},
});

/** One server jump/search hit (shared by the nav jump box + #06a Quick Open). Unified across
 * the two sources: outline (arc/chapter/scene, with a breadcrumb `path`) and flat chapters. */
export interface JumpResult {
  id: string;
  kind: ManuscriptRowKind;
  title: string;
  number: number | null;    // chapter display number (book sort_order / outline story_order)
  status: string | null;
  chapterId: string | null;
  path: string[];           // ancestor-title breadcrumb (outline); [] for flat chapters
}

/** A jump hit → a minimal node for the existing onSelect(node) contract (highlight / #03 dock). */
export function jumpResultToNode(r: JumpResult): ManuscriptNode {
  return {
    id: r.id, kind: r.kind, title: r.title, number: r.number, status: r.status,
    chapterId: r.chapterId, hasChildren: false, childCount: null,
  };
}
