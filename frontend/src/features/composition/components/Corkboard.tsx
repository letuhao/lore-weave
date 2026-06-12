// LOOM Composition (T1.1d) — the Corkboard: the cards layout of the Outline
// panel (T1.1). Scenes are index cards grouped into labeled per-chapter bands;
// drag to reorder within a chapter or across chapters (reparent), reusing the
// T1.1c reorder endpoint. A pure cards-over-the-same-`useOutline`-nodes view —
// no new store. Owned by OutlineTree (shared host + handlers).
import { useTranslation } from 'react-i18next';
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter, useDroppable, useSensor, useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, sortableKeyboardCoordinates, rectSortingStrategy } from '@dnd-kit/sortable';
import { SceneCard } from './SceneCard';
import type { OutlineNode } from '../types';

export type ChapterBand = { chapter: OutlineNode; scenes: OutlineNode[] };
export type CardMove = { nodeId: string; new_parent_id: string; after_id: string | null };

// Pure (exported for tests): group active scenes under their chapters, chapters
// in tree (pre-order) order, scenes in reading order (story_order NULLS LAST,
// then rank). Archived nodes are excluded (the cards view is active-only;
// restore stays in the tree view). Chapters with no scenes still get a band.
export function groupScenesByChapter(nodes: OutlineNode[]): ChapterBand[] {
  const active = nodes.filter((n) => !n.is_archived);
  const byParent = new Map<string | null, OutlineNode[]>();
  for (const n of active) {
    const arr = byParent.get(n.parent_id) ?? [];
    arr.push(n);
    byParent.set(n.parent_id, arr);
  }
  const rankCmp = (a: OutlineNode, b: OutlineNode) =>
    a.rank !== b.rank ? (a.rank < b.rank ? -1 : 1) : (a.id < b.id ? -1 : 1);
  const sceneCmp = (a: OutlineNode, b: OutlineNode) => {
    if (a.story_order !== b.story_order) {
      if (a.story_order == null) return 1;
      if (b.story_order == null) return -1;
      return a.story_order - b.story_order;
    }
    return rankCmp(a, b);
  };
  // Pre-order walk collecting chapters in their tree position (arc rank → chapter
  // rank), so the bands read top-to-bottom like the outline.
  const chapters: OutlineNode[] = [];
  const walk = (parent: string | null) => {
    for (const n of (byParent.get(parent) ?? []).slice().sort(rankCmp)) {
      if (n.kind === 'chapter') chapters.push(n);
      if (n.kind === 'arc' || n.kind === 'chapter') walk(n.id);
    }
  };
  walk(null);
  return chapters.map((chapter) => ({
    chapter,
    scenes: (byParent.get(chapter.id) ?? []).filter((n) => n.kind === 'scene').sort(sceneCmp),
  }));
}

// Pure (exported for tests): resolve a drag (active card dropped onto `overId` —
// another card OR a `band:<chapterId>` droppable for an empty chapter) to a
// reorder move, or null if not found / a no-op (same node). A same-chapter drop
// uses dnd-kit's sortable semantics (active TAKES over's slot — arrayMove), so a
// downward drag lands AFTER `over`; a cross-chapter drop inserts before `over`
// (the active card wasn't in that band, so there's no direction ambiguity).
export function computeCardMove(bands: ChapterBand[], activeId: string, overId: string): CardMove | null {
  if (activeId === overId) return null;
  let activeChapter: string | null = null;
  for (const b of bands) if (b.scenes.some((s) => s.id === activeId)) { activeChapter = b.chapter.id; break; }
  if (activeChapter === null) return null;

  if (overId.startsWith('band:')) {
    const targetChapter = overId.slice(5);
    const band = bands.find((b) => b.chapter.id === targetChapter);
    if (!band) return null;
    const afterId = band.scenes.length ? band.scenes[band.scenes.length - 1].id : null; // append
    return { nodeId: activeId, new_parent_id: targetChapter, after_id: afterId };
  }

  const band = bands.find((b) => b.scenes.some((s) => s.id === overId));
  if (!band) return null;
  const targetChapter = band.chapter.id;
  let afterId: string | null;
  if (targetChapter === activeChapter) {
    const ids = band.scenes.map((s) => s.id);
    const moved = ids.slice();
    moved.splice(ids.indexOf(overId), 0, moved.splice(ids.indexOf(activeId), 1)[0]); // arrayMove
    const at = moved.indexOf(activeId);
    afterId = at > 0 ? moved[at - 1] : null;
  } else {
    const overPos = band.scenes.findIndex((s) => s.id === overId);
    afterId = overPos > 0 ? band.scenes[overPos - 1].id : null; // insert before `over`
  }
  return { nodeId: activeId, new_parent_id: targetChapter, after_id: afterId };
}

function EmptyBand({ chapterId, label }: { chapterId: string; label: string }) {
  const { setNodeRef, isOver } = useDroppable({ id: `band:${chapterId}` });
  const { t } = useTranslation('composition');
  return (
    <div
      ref={setNodeRef}
      data-testid="corkboard-empty-band"
      className={'rounded-md border border-dashed p-3 text-[11px] text-muted-foreground ' + (isOver ? 'bg-secondary/40' : '')}
    >
      {t('corkboard.emptyBand', { defaultValue: 'No scenes in {{chapter}} — add a card.', chapter: label })}
    </div>
  );
}

export function Corkboard({
  nodes, editingId, draggable,
  onSelect, onAddCard, onEditStart, onEditCommit, onEditCancel, onArchive, onCycleStatus, onReorder,
}: {
  nodes: OutlineNode[];
  editingId: string | null;
  draggable: boolean;
  onSelect: (scene: OutlineNode) => void;
  onAddCard: (chapter: OutlineNode) => void;
  onEditStart: (id: string) => void;
  onEditCommit: (scene: OutlineNode, title: string, synopsis: string) => void;
  onEditCancel: () => void;
  onArchive: (scene: OutlineNode) => void;
  onCycleStatus: (scene: OutlineNode, status: OutlineNode['status']) => void;
  onReorder: (move: CardMove) => void;
}) {
  const { t } = useTranslation('composition');
  const bands = groupScenesByChapter(nodes);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const handleDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over) return;
    const move = computeCardMove(bands, String(active.id), String(over.id));
    if (move) onReorder(move);
  };

  if (bands.length === 0) {
    return (
      <div data-testid="corkboard-empty" className="p-3 text-xs text-muted-foreground">
        {t('corkboard.empty', { defaultValue: 'No chapters yet. Plan chapters first, then add scene cards.' })}
      </div>
    );
  }

  // One SortableContext across ALL cards (flat, in band order) so a card can be
  // dragged between chapters; empty chapters get their own droppable band.
  const allSceneIds = bands.flatMap((b) => b.scenes.map((s) => s.id));
  return (
    <div className="flex-1 overflow-y-auto p-2" data-testid="composition-corkboard">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={allSceneIds} strategy={rectSortingStrategy}>
          {bands.map(({ chapter, scenes }) => (
            <div key={chapter.id} className="mb-3" data-testid="corkboard-band" data-chapter={chapter.id}>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[11px] font-medium text-muted-foreground">
                  {chapter.title || t('corkboard.untitledChapter', { defaultValue: 'Untitled chapter' })}
                </span>
                <button
                  type="button"
                  data-testid="corkboard-add-card"
                  aria-label={t('corkboard.addCard', { defaultValue: 'Add card' })}
                  className="text-[11px] text-muted-foreground hover:text-foreground"
                  onClick={() => onAddCard(chapter)}
                >
                  + {t('corkboard.addCard', { defaultValue: 'Add card' })}
                </button>
              </div>
              {scenes.length === 0 ? (
                <EmptyBand chapterId={chapter.id} label={chapter.title || ''} />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {scenes.map((scene) => (
                    <SceneCard
                      key={scene.id}
                      scene={scene}
                      editing={editingId === scene.id}
                      draggable={draggable}
                      onSelect={() => onSelect(scene)}
                      onEditStart={() => onEditStart(scene.id)}
                      onEditCommit={(title, syn) => onEditCommit(scene, title, syn)}
                      onEditCancel={onEditCancel}
                      onArchive={() => onArchive(scene)}
                      onCycleStatus={(status) => onCycleStatus(scene, status)}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </SortableContext>
      </DndContext>
    </div>
  );
}
