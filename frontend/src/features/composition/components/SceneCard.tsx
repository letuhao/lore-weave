// LOOM Composition (T1.1d) — one Corkboard index card (a scene). Render-only:
// title + synopsis + status dot, with hover affordances (edit title+synopsis,
// archive, status-cycle) and a drag grip. Mirrors OutlineNodeRow's idioms
// (status DOT, fire-once edit latch, sortable grip). Card body click → open the
// scene; the grip (not the body) starts a drag, so a click still navigates.
import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { OutlineNode } from '../types';

const DOT: Record<OutlineNode['status'], string> = {
  done: '●', drafting: '◐', outline: '○', empty: '○',
};
const STATUS_CYCLE: OutlineNode['status'][] = ['empty', 'outline', 'drafting', 'done'];
const nextStatus = (s: OutlineNode['status']): OutlineNode['status'] =>
  STATUS_CYCLE[(STATUS_CYCLE.indexOf(s) + 1) % STATUS_CYCLE.length];

export function SceneCard({
  scene, editing, draggable,
  onSelect, onEditStart, onEditCommit, onEditCancel, onArchive, onCycleStatus,
}: {
  scene: OutlineNode;
  editing: boolean;
  draggable: boolean;
  onSelect: () => void;
  onEditStart: () => void;
  onEditCommit: (title: string, synopsis: string) => void;
  onEditCancel: () => void;
  onArchive: () => void;
  onCycleStatus: (status: OutlineNode['status']) => void;
}) {
  const { t } = useTranslation('composition');
  const titleRef = useRef<HTMLInputElement | null>(null);
  const synRef = useRef<HTMLTextAreaElement | null>(null);
  const done = useRef(false); // fire-once latch (see OutlineNodeRow)
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: scene.id, disabled: !draggable || editing });

  const finish = (fn: () => void) => { if (done.current) return; done.current = true; fn(); };
  const commit = () => finish(() => {
    const title = titleRef.current?.value.trim() ?? '';
    const syn = synRef.current?.value ?? '';
    if (title !== scene.title || syn !== scene.synopsis) onEditCommit(title || scene.title, syn);
    else onEditCancel();
  });
  const cancel = () => finish(onEditCancel);

  return (
    <div
      ref={setNodeRef}
      data-testid="corkboard-card"
      data-status={scene.status}
      className={
        'group flex w-44 flex-col gap-1 rounded-md border bg-card p-2 text-xs shadow-sm '
        + (isDragging ? 'opacity-60 ' : '')
      }
      style={{ transform: CSS.Transform.toString(transform), transition, ...(isDragging ? { zIndex: 1 } : {}) }}
    >
      {editing ? (
        <div className="flex flex-col gap-1">
          <input
            ref={(el) => { titleRef.current = el; if (el) done.current = false; }}
            data-testid="corkboard-card-title-input"
            defaultValue={scene.title}
            autoFocus
            aria-label={t('corkboard.editTitle', { defaultValue: 'Card title' })}
            className="rounded border bg-background px-1 py-0.5 text-xs font-medium"
            onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); cancel(); } }}
          />
          <textarea
            ref={synRef}
            data-testid="corkboard-card-synopsis-input"
            defaultValue={scene.synopsis}
            rows={3}
            aria-label={t('corkboard.editSynopsis', { defaultValue: 'Card synopsis' })}
            className="resize-none rounded border bg-background px-1 py-0.5 text-[11px]"
            onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); cancel(); } }}
          />
          <div className="flex justify-end gap-1">
            <button type="button" data-testid="corkboard-card-cancel" className="px-1 text-[10px] text-muted-foreground hover:text-foreground" onClick={cancel}>
              {t('cancel', { defaultValue: 'Cancel' })}
            </button>
            <button type="button" data-testid="corkboard-card-save" className="px-1 text-[10px] text-primary hover:underline" onClick={commit}>
              {t('save', { defaultValue: 'Save' })}
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-start gap-1">
            {draggable ? (
              <button
                type="button"
                data-testid="corkboard-card-drag"
                aria-label={t('outline.drag', { defaultValue: 'Drag to reorder' })}
                className="shrink-0 cursor-grab text-[10px] text-muted-foreground opacity-0 hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100 active:cursor-grabbing"
                {...attributes}
                {...listeners}
              >
                ⠿
              </button>
            ) : null}
            <button
              type="button"
              data-testid="corkboard-card-open"
              className="min-w-0 flex-1 truncate text-left font-medium hover:text-primary"
              onClick={onSelect}
            >
              {scene.title || t('untitledScene', { defaultValue: 'Untitled scene' })}
            </button>
          </div>
          {scene.synopsis ? (
            <p className="line-clamp-3 text-[11px] text-muted-foreground">{scene.synopsis}</p>
          ) : (
            <p className="text-[11px] italic text-muted-foreground/60">{t('corkboard.noSynopsis', { defaultValue: 'No synopsis' })}</p>
          )}
          <div className="mt-auto flex items-center justify-between pt-1">
            <button
              type="button"
              data-testid="corkboard-card-status"
              title={t('outline.cycleStatus', { defaultValue: 'Cycle status' })}
              aria-label={t('outline.cycleStatus', { defaultValue: 'Cycle status' })}
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => onCycleStatus(nextStatus(scene.status))}
            >
              <span aria-hidden>{DOT[scene.status]}</span>
            </button>
            <div className="flex items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
              <button type="button" data-testid="corkboard-card-edit" aria-label={t('outline.rename', { defaultValue: 'Edit' })} className="text-[10px] text-muted-foreground hover:text-foreground" onClick={onEditStart}>✎</button>
              <button type="button" data-testid="corkboard-card-archive" aria-label={t('outline.archive', { defaultValue: 'Archive' })} className="text-[10px] text-muted-foreground hover:text-destructive" onClick={onArchive}>✕</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
