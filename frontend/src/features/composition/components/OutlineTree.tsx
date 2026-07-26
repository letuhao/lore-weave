// LOOM Composition (T1.1a/b) — committed-outline tree browser.
//
// A persistent Act→Chapter→Scene browser of the committed outline (GET /outline),
// hosted as a left-panel tab in ChapterEditorPage. T1.1a: status dots,
// collapse/expand, chapter-level navigation. T1.1b: node CRUD — inline rename,
// add-child (chapter→scene, scene→beat), soft-archive, scene status-cycle, with
// If-Match optimistic concurrency (a 412 NODE_VERSION_CONFLICT refetches the
// server's current row, never silently losing a concurrent edit). dnd-kit reorder
// (T1.1c) and the cards⇄tree toggle / Corkboard (T1.1d) are follow-up slices.
// Resolves the composition Work from bookId itself (react-query dedups with
// CompositionPanel's resolution).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { useWorkResolution } from '../hooks/useWork';
import { useActiveWorkId } from '../hooks/useActiveWork';
import { resolveActiveWork } from '../workSelect';
import { useOutline, useOutlineMutations } from '../hooks/useOutline';
import { OutlineNodeRow } from './OutlineNodeRow';
import { Corkboard, type CardMove } from './Corkboard';
import type { OutlineNode } from '../types';

// kind → the kind a node of this kind must be parented under (fixed-depth tree).
const PARENT_KIND: Record<OutlineNode['kind'], OutlineNode['kind'] | null> = {
  arc: null, chapter: 'arc', scene: 'chapter', beat: 'scene',
};

// Pure (exported for tests): given the flat display rows + a drag (active dropped
// onto over), compute the move for the active node — {nodeId, new_parent_id,
// after_id} — or null if the drop is a no-op / invalid. Because every kind has a
// fixed depth, the new parent is just the nearest preceding node of the active's
// parent-kind in the post-move order (so a scene can only land under a chapter —
// inherently kind-safe); after_id is the nearest preceding sibling already under
// that parent (null = first child).
export function computeReorder(
  rows: { node: OutlineNode }[],
  activeId: string,
  overId: string,
): { nodeId: string; new_parent_id: string | null; after_id: string | null } | null {
  if (activeId === overId) return null;
  const nodes = rows.map((r) => r.node);
  const from = nodes.findIndex((n) => n.id === activeId);
  const to = nodes.findIndex((n) => n.id === overId);
  if (from < 0 || to < 0) return null;
  const active = nodes[from];
  const parentKind = PARENT_KIND[active.kind];

  const ordered = nodes.slice();
  ordered.splice(to, 0, ordered.splice(from, 1)[0]); // prospective post-drag order
  const at = ordered.findIndex((n) => n.id === activeId);

  let newParent: string | null = null;
  if (parentKind !== null) {
    for (let i = at - 1; i >= 0; i--) {
      if (ordered[i].kind === parentKind) { newParent = ordered[i].id; break; }
    }
    if (newParent === null) return null; // e.g. a scene dragged above the first chapter
  }
  let afterId: string | null = null;
  for (let i = at - 1; i >= 0; i--) {
    if (ordered[i].id === newParent) break; // reached the parent → first child
    if (ordered[i].kind === active.kind && ordered[i].parent_id === newParent) { afterId = ordered[i].id; break; }
  }
  return { nodeId: activeId, new_parent_id: newParent, after_id: afterId };
}

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
  const { data: activeWorkId } = useActiveWorkId(bookId, token);
  // EC-3d: resolve the ACTIVE Work (per-book pref, else canonical) so the outline
  // tree follows a "Switch to" a dị bản instead of pinning to canon.
  const work = resolveActiveWork(resolution.data, activeWorkId);
  const [showArchived, setShowArchived] = useState(false);
  const [viewMode, setViewMode] = useState<'tree' | 'cards'>('tree');
  // Cards (Corkboard) read only active scenes; the archived view is tree-only.
  const q = useOutline(work?.project_id, token, showArchived && viewMode === 'tree');
  const m = useOutlineMutations(work?.project_id, token);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);

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

  // T1.1b — a stale If-Match edit 412s (NODE_VERSION_CONFLICT). Surface it + pull
  // the server's current row so the tree never silently drops a concurrent edit.
  const onError = (e: unknown) => {
    if ((e as { status?: number }).status === 412) {
      toast.warning(t('outline.conflict', { defaultValue: 'This node was edited elsewhere — refreshed.' }));
      m.invalidate();
    } else {
      toast.error((e as Error).message);
    }
  };
  const rename = (node: OutlineNode, title: string) => {
    setEditingId(null);
    m.rename.mutate({ nodeId: node.id, title, version: node.version }, { onError });
  };
  const cycleStatus = (node: OutlineNode, status: OutlineNode['status']) =>
    m.setStatus.mutate({ nodeId: node.id, status, version: node.version }, { onError });
  // Add a child + immediately open it for rename (new nodes are created with an
  // empty title, so without this they'd all read "scene"/"beat" until edited).
  // Also expand the parent so the new child is visible.
  const addChild = (node: OutlineNode, kind: 'scene' | 'beat') =>
    m.addChild.mutate(
      { kind, parent_id: node.id, chapter_id: kind === 'scene' ? node.chapter_id : null, title: '' },
      {
        onError,
        onSuccess: (created: OutlineNode) => {
          setCollapsed((prev) => {
            if (!prev.has(node.id)) return prev;
            const next = new Set(prev);
            next.delete(node.id);
            return next;
          });
          setEditingId(created.id);
        },
      },
    );
  // Archiving cascades to the whole subtree (BE recursive CTE). It's reversible
  // (restore below), but to avoid a one-click cascade we confirm when the node
  // has children (matches the app's confirm() convention); leaves archive
  // directly.
  const archive = (node: OutlineNode, hasChildren: boolean) => {
    if (hasChildren && !window.confirm(
      t('outline.archiveConfirm', {
        defaultValue: 'Archive "{{title}}" and everything inside it?',
        title: node.title || node.kind,
      }),
    )) return;
    if (editingId === node.id) setEditingId(null);
    m.archive.mutate(node.id, { onError });
  };
  const restore = (node: OutlineNode) => m.restore.mutate(node.id, { onError });
  // T1.1d Corkboard handlers (over the same nodes + mutations as the tree).
  const editCard = (scene: OutlineNode, title: string, synopsis: string) => {
    setEditingId(null);
    m.editCard.mutate({ nodeId: scene.id, title, synopsis, version: scene.version }, { onError });
  };
  const reorderCard = (move: CardMove) => {
    const node = (q.data ?? []).find((n) => n.id === move.nodeId);
    if (!node) return;
    m.reorder.mutate(
      { nodeId: move.nodeId, new_parent_id: move.new_parent_id, after_id: move.after_id, version: node.version },
      { onError },
    );
  };

  // T1.1c — drag sensors. A 5px activation distance keeps a click (select/nav)
  // from starting a drag; the keyboard sensor makes reorder a11y-operable.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  if (resolution.isLoading || (q.isLoading && !q.data)) {
    return <div className="p-3 text-xs text-muted-foreground">{t('loading', { defaultValue: 'Loading…' })}</div>;
  }
  // `!work` → no outline can exist; the empty body still keeps the header (and its
  // "show archived" toggle) reachable so an all-archived tree can be revealed.
  const rows = flattenOutline(q.data ?? [], collapsed);
  // Reorder only in the default view (the archived view is for restore, not drag).
  const draggable = !showArchived;
  const handleDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over) return;
    const move = computeReorder(rows, String(active.id), String(over.id));
    if (!move) return;
    const node = rows.find((r) => r.node.id === move.nodeId)?.node;
    if (!node) return;
    m.reorder.mutate(
      { nodeId: move.nodeId, new_parent_id: move.new_parent_id, after_id: move.after_id, version: node.version },
      { onError },
    );
  };
  return (
    <div className="flex flex-1 flex-col overflow-hidden" data-testid="composition-outline">
      <div className="flex flex-shrink-0 items-center justify-between border-b px-3 py-2 text-[10px] text-muted-foreground">
        <span>{t('outline.title', { defaultValue: 'Outline' })}</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="outline-toggle-view"
            aria-pressed={viewMode === 'cards'}
            className="rounded px-1.5 py-0.5 hover:text-foreground"
            onClick={() => setViewMode((v) => (v === 'tree' ? 'cards' : 'tree'))}
          >
            {viewMode === 'tree'
              ? t('outline.viewCards', { defaultValue: 'Cards' })
              : t('outline.viewTree', { defaultValue: 'Tree' })}
          </button>
          {viewMode === 'tree' && (
            <button
              type="button"
              data-testid="outline-toggle-archived"
              aria-pressed={showArchived}
              className={'rounded px-1.5 py-0.5 hover:text-foreground ' + (showArchived ? 'text-foreground' : '')}
              onClick={() => setShowArchived((v) => !v)}
            >
              {showArchived
                ? t('outline.hideArchived', { defaultValue: 'Hide archived' })
                : t('outline.showArchived', { defaultValue: 'Show archived' })}
            </button>
          )}
        </div>
      </div>
      {viewMode === 'cards' ? (
        <Corkboard
          nodes={q.data ?? []}
          editingId={editingId}
          draggable
          onSelect={select}
          onAddCard={(chapter) => addChild(chapter, 'scene')}
          onEditStart={(id) => setEditingId(id)}
          onEditCommit={editCard}
          onEditCancel={() => setEditingId(null)}
          onArchive={(scene) => archive(scene, (q.data ?? []).some((n) => n.parent_id === scene.id && !n.is_archived))}
          onCycleStatus={cycleStatus}
          onReorder={reorderCard}
        />
      ) : rows.length === 0 ? (
        <div data-testid="outline-empty" className="p-3 text-xs text-muted-foreground">
          {t('outline.empty', { defaultValue: 'No outline yet. Use the Planner (right panel) to decompose chapters into scenes.' })}
        </div>
      ) : (
      <div className="flex-1 overflow-y-auto py-1">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={rows.map((r) => r.node.id)} strategy={verticalListSortingStrategy}>
            {rows.map(({ node, depth, hasChildren }) => (
              <OutlineNodeRow
                key={node.id}
                node={node}
                depth={depth}
                hasChildren={hasChildren}
                expanded={!collapsed.has(node.id)}
                isCurrent={node.kind === 'chapter' && node.chapter_id === currentChapterId}
                editing={editingId === node.id}
                draggable={draggable && !node.is_archived}
                onToggle={() => toggle(node.id)}
                onSelect={() => select(node)}
                onRenameStart={() => setEditingId(node.id)}
                onRenameCommit={(title) => rename(node, title)}
                onRenameCancel={() => setEditingId(null)}
                onAddChild={(kind) => addChild(node, kind)}
                onArchive={() => archive(node, hasChildren)}
                onCycleStatus={(status) => cycleStatus(node, status)}
                onRestore={() => restore(node)}
              />
            ))}
          </SortableContext>
        </DndContext>
      </div>
      )}
    </div>
  );
}
