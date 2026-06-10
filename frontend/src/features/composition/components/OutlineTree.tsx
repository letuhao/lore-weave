// LOOM Composition (T1.1a) — committed-outline tree browser (read + navigate).
//
// A persistent Act→Chapter→Scene browser of the committed outline (GET /outline),
// hosted as a left-panel tab in ChapterEditorPage. Read-only slice: status dots,
// collapse/expand, and chapter-level navigation (click a node → open its
// chapter). Node CRUD (T1.1b), dnd-kit reorder (T1.1c), and the cards⇄tree
// toggle / Corkboard (T1.1d) are follow-up slices. Resolves the composition Work
// from bookId itself (react-query dedups with CompositionPanel's resolution).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useWorkResolution } from '../hooks/useWork';
import { useOutline } from '../hooks/useOutline';
import { OutlineNodeRow } from './OutlineNodeRow';
import type { OutlineNode } from '../types';

// Pure: flatten the committed nodes into a depth-annotated pre-order list,
// skipping the children of collapsed parents. Ordered by story_order within a
// parent. Exported for unit tests.
export function flattenOutline(
  nodes: OutlineNode[],
  collapsed: Set<string>,
): { node: OutlineNode; depth: number; hasChildren: boolean }[] {
  const byParent = new Map<string | null, OutlineNode[]>();
  for (const n of nodes) {
    const arr = byParent.get(n.parent_id) ?? [];
    arr.push(n);
    byParent.set(n.parent_id, arr);
  }
  // Mirror the BE canonical order (outline.py: ORDER BY story_order NULLS LAST,
  // rank COLLATE "C", id). Chapters/arcs have no story_order, so they order by
  // `rank`, NOT insertion order (REVIEW-IMPL MED-3).
  const cmp = (a: OutlineNode, b: OutlineNode) => {
    if (a.story_order !== b.story_order) {
      if (a.story_order == null) return 1; // nulls last
      if (b.story_order == null) return -1;
      return a.story_order - b.story_order;
    }
    if (a.rank !== b.rank) return (a.rank ?? '') < (b.rank ?? '') ? -1 : 1;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  };
  for (const arr of byParent.values()) arr.sort(cmp);
  const out: { node: OutlineNode; depth: number; hasChildren: boolean }[] = [];
  const seen = new Set<string>(); // defensive: a duplicate/cyclic id never renders twice
  const walk = (parent: string | null, depth: number) => {
    for (const n of byParent.get(parent) ?? []) {
      if (seen.has(n.id)) continue;
      seen.add(n.id);
      const hasChildren = byParent.has(n.id);
      out.push({ node: n, depth, hasChildren });
      if (hasChildren && !collapsed.has(n.id)) walk(n.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

export function OutlineTree(
  { bookId, token, currentChapterId, onNavigateChapter }:
  { bookId: string; token: string | null; currentChapterId: string; onNavigateChapter: (chapterId: string) => void },
) {
  const { t } = useTranslation('composition');
  const resolution = useWorkResolution(bookId, token);
  const res = resolution.data;
  const work = res?.status === 'found' ? res.work : res?.status === 'candidates' ? (res.candidates[0] ?? null) : null;
  const q = useOutline(work?.project_id, token);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // T1.1a — chapter-level navigation (precise scroll-to-scene deferred).
  const select = (node: OutlineNode) => {
    if (node.chapter_id) onNavigateChapter(node.chapter_id);
  };

  if (resolution.isLoading || q.isLoading) {
    return <div className="p-3 text-xs text-muted-foreground">{t('loading', { defaultValue: 'Loading…' })}</div>;
  }
  if (!work || (q.data?.length ?? 0) === 0) {
    return (
      <div data-testid="outline-empty" className="p-3 text-xs text-muted-foreground">
        {t('outline.empty', { defaultValue: 'No outline yet. Use the Planner (right panel) to decompose chapters into scenes.' })}
      </div>
    );
  }

  const rows = flattenOutline(q.data ?? [], collapsed);
  return (
    <div className="flex flex-1 flex-col overflow-hidden" data-testid="composition-outline">
      <div className="flex-shrink-0 border-b px-3 py-2 text-[10px] text-muted-foreground">
        {t('outline.title', { defaultValue: 'Outline' })}
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {rows.map(({ node, depth, hasChildren }) => (
          <OutlineNodeRow
            key={node.id}
            node={node}
            depth={depth}
            hasChildren={hasChildren}
            expanded={!collapsed.has(node.id)}
            isCurrent={node.kind === 'chapter' && node.chapter_id === currentChapterId}
            onToggle={() => toggle(node.id)}
            onSelect={() => select(node)}
          />
        ))}
      </div>
    </div>
  );
}
