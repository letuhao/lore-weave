// Manuscript navigator (#02) — source-agnostic tree model.
//
// The tree is fed by TWO sources (see useManuscriptTree): a book with no composition Work
// renders a FLAT chapter list from book-service (cursor-paged); a book WITH a Work renders
// the composition outline as arc → chapter → scene (lazy-paged children). Both produce the
// same ManuscriptNode/Row shapes so the view is one component.

export type ManuscriptRowKind = 'arc' | 'chapter' | 'scene';

/** A node in the in-memory manuscript tree. */
export interface ManuscriptNode {
  id: string;                 // stable row id (book chapter id, or outline node id)
  kind: ManuscriptRowKind;
  title: string;
  number: number | null;      // chapter display number (book sort_order); null for arc/scene
  status: string | null;      // outline status (scene/chapter); null otherwise
  chapterId: string | null;   // the BOOK chapter this row opens (arc → null). Dock target.
  hasChildren: boolean;       // can be expanded to lazy-load children
}

/** A flattened render row: either a tree node, or a "load more" affordance for a parent
 * that has an unfetched next page (root or an expanded node's children). */
export type ManuscriptRow =
  | { type: 'node'; node: ManuscriptNode; depth: number; expanded: boolean; loading: boolean }
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
