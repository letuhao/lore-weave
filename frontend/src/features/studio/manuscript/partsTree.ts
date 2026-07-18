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
      title: g.unassigned ? 'Unassigned' : g.title || '(untitled act)',
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
