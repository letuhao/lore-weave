// S-02 — build a fully-loaded manuscript TreeState from (parts, chapters).
//
// The flat-chapter navigator normally cursor-pages chapters straight under ROOT. When
// a book has acts (parts), we instead render a TWO-LEVEL tree: each active act is a
// group header ('part' node) with its chapters nested, followed by an "Unassigned"
// bucket for part_id IS NULL. Because grouping needs every chapter's part_id up front,
// useManuscriptTree loads ALL chapters for a parts-enabled book (bounded) and hands
// them here — so the tree is fully loaded (no per-part cursor, no 'more' rows).
//
// Pure + deterministic ⇒ unit-testable without React or a DB.
import i18n from '@/i18n';
import { groupChaptersByParts, type Part, type ChapterLike } from './partsApi';
import { ROOT_KEY, emptyTree, type ManuscriptNode, type TreeState } from './types';

/** Sentinel node id for the synthetic "Unassigned" (flat-manuscript) bucket. Not a UUID,
 *  so it can never collide with a real part_id. */
export const PART_UNASSIGNED_ID = '__unassigned__';

/**
 * A chapter's DISPLAY title — the ONE home shared by both navigator mappers (flat `chapterToNode`
 * and the parts tree) so the two never drift. A named chapter shows its title; an unnamed one shows
 * a localized "Chapter {n}" (from its sort_order) — NEVER the storage filename `editor-<uuid>.txt`,
 * which read as a chapter title in the first-run diary (F4). Pure fn ⇒ localized via the i18n
 * singleton (no React hook available here).
 */
export function chapterDisplayTitle(c: { title?: string | null; sort_order: number }): string {
  const named = c.title?.trim();
  if (named) return named;
  return i18n.t('studio:manuscript.chapterN', { number: c.sort_order, defaultValue: 'Chapter {{number}}' });
}

function chapterNode(c: ChapterLike): ManuscriptNode {
  return {
    id: c.chapter_id,
    kind: 'chapter',
    title: chapterDisplayTitle(c),
    number: c.sort_order,
    status: null,
    chapterId: c.chapter_id,
    hasChildren: false,
    childCount: null,
  };
}

/**
 * buildPartsTree — a fully-loaded TreeState with act group headers + nested chapters +
 * an Unassigned bucket. Acts are expanded by default (you want to see your manuscript);
 * every cursor is null (nothing lazy-loads). alwaysShowUnassigned keeps the flat bucket
 * visible even when empty, so an empty/parts-only book still shows a drop target.
 */
export function buildPartsTree(parts: Part[], chapters: ChapterLike[]): TreeState {
  const groups = groupChaptersByParts(parts, chapters, { alwaysShowUnassigned: true });
  const t = emptyTree();
  const rootChildren: string[] = [];

  for (const g of groups) {
    const groupId = g.unassigned ? PART_UNASSIGNED_ID : (g.partId as string);
    const chapterNodes = g.chapters.map(chapterNode);
    t.nodes[groupId] = {
      id: groupId,
      kind: 'part',
      title: g.unassigned
        ? i18n.t('studio:manuscript.unassignedBucket', { defaultValue: 'Unassigned' })
        : g.title || i18n.t('studio:manuscript.untitledAct', { defaultValue: '(untitled part)' }),
      number: null,
      status: g.unassigned ? 'unassigned' : null, // status carries the bucket flag for the renderer
      chapterId: null,
      hasChildren: chapterNodes.length > 0,
      childCount: chapterNodes.length,
    };
    rootChildren.push(groupId);
    t.childrenOf[groupId] = chapterNodes.map((n) => n.id);
    t.childCursor[groupId] = null; // fully loaded
    t.expanded[groupId] = true; // acts open by default
    for (const n of chapterNodes) t.nodes[n.id] = n;
  }

  t.childrenOf[ROOT_KEY] = rootChildren;
  t.childCursor[ROOT_KEY] = null;
  return t;
}

/** True when a node id is the Unassigned bucket (renderer: no rename/trash affordance). */
export function isUnassignedBucket(nodeId: string): boolean {
  return nodeId === PART_UNASSIGNED_ID;
}

/**
 * D-STUDIO-CHAPTER-OUTSIDE-THE-PLAN — append a "Not in the plan" bucket to an OUTLINE tree.
 *
 * The outline lens renders `outline_node` rows, so a chapter the plan does not claim appeared
 * NOWHERE in the rail. To an author, a chapter they cannot see is a chapter they have lost —
 * which is exactly what happened live: a chapter created in a planned book was absent from the
 * tree AND from both searches.
 *
 * Coverage is decided by the server (`outline_stats.linked_chapter_ids`, keyed on the node's own
 * `chapter_id`) because the outline loads lazily — the node carrying a link can sit at any depth,
 * so the client cannot answer this from the tree it has.
 *
 * Appended LAST and expanded, mirroring the parts lens's Unassigned bucket. Empty ⇒ unchanged:
 * unlike the parts bucket there is no drop-target reason to show it, and a permanent empty row
 * in every planned book is noise.
 */
export function appendUnplannedChapters(state: TreeState, chapters: ChapterLike[]): TreeState {
  if (chapters.length === 0) return state;
  const nodes = chapters.map(chapterNode);
  const t: TreeState = {
    nodes: { ...state.nodes },
    childrenOf: { ...state.childrenOf },
    childCursor: { ...state.childCursor },
    expanded: { ...state.expanded },
    loading: { ...state.loading },
  };
  t.nodes[PART_UNASSIGNED_ID] = {
    id: PART_UNASSIGNED_ID,
    kind: 'part',
    title: i18n.t('studio:manuscript.notInPlanBucket', { defaultValue: 'Not in the plan' }),
    number: null,
    status: 'unassigned', // the renderer's bucket flag (no rename/trash affordance)
    chapterId: null,
    hasChildren: true,
    childCount: nodes.length,
  };
  for (const n of nodes) t.nodes[n.id] = n;
  t.childrenOf[PART_UNASSIGNED_ID] = nodes.map((n) => n.id);
  t.childCursor[PART_UNASSIGNED_ID] = null; // fully loaded, nothing to page
  t.expanded[PART_UNASSIGNED_ID] = true;
  t.childrenOf[ROOT_KEY] = [...(state.childrenOf[ROOT_KEY] ?? []), PART_UNASSIGNED_ID];
  return t;
}
