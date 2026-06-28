// W10 §5.4 — the DESKTOP arc-timeline edit-grid (the thread × chapter drag-grid the
// W6 audit flagged as "0 keyboard / 0 touch"). Builds against the FROZEN
// ArcTimelineContract; emits the same ArcTimelineEdit actions the mobile list does, so
// the two surfaces stay in lock-step (the shared pure reducer applies them).
//
// Interaction (both honored):
//   • KEYBOARD (mandatory, §5.4): Tab to a placement → Enter/Space grab → Arrow move /
//     Shift+Arrow resize the end edge / ArrowUp·Down change thread / Enter drop / Esc
//     release. Each placement is a focusable button with aria-grabbed + an
//     aria-describedby announcing "combat thread, chapters 2-3"; a polite live-region
//     narrates the grab.
//   • POINTER (dnd-kit, the studio idiom): drag a placement across chapters/threads →
//     a `move` edit (chapter delta from the drag distance, thread from the row dropped on).
//
// Render-only against the contract; all logic flows through `onEdit`. The grid is
// DESKTOP-only (the responsive ArcTimelineEditor swaps in the mobile list below md).
import { useRef, useState } from 'react';
import {
  DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { useTranslation } from 'react-i18next';
import type { ArcThread, ArcTimelineContract, ArcTimelineEdit, ArcPlacement } from '../arcTimelineContract';
import { dragEndToMoveEdit } from '../applyArcEdit';

const THREAD_DROP_PREFIX = 'arc-thread:';

export function ArcTimelineGrid({
  threads, placements, chapterSpan, onEdit, editGridEnabled,
}: ArcTimelineContract) {
  const { t } = useTranslation('composition');
  const [grabbedId, setGrabbedId] = useState<string | null>(null);
  const [announce, setAnnounce] = useState('');
  // measured pixel width of one chapter column — drives the pointer-drag chapter delta.
  const trackRef = useRef<HTMLDivElement | null>(null);
  const editable = editGridEnabled && !!onEdit;
  const cols = Math.max(1, chapterSpan);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  function handleDragEnd(ev: DragEndEvent) {
    if (!onEdit) return;
    const id = String(ev.active.id);
    const p = placements.find((x) => x.id === id);
    if (!p) return;
    const overId = ev.over ? String(ev.over.id) : '';
    const edit = dragEndToMoveEdit({
      placementId: id,
      fromThread: p.thread,
      deltaX: ev.delta.x,
      trackWidth: trackRef.current?.offsetWidth ?? 0,
      cols,
      overThread: overId.startsWith(THREAD_DROP_PREFIX) ? overId.slice(THREAD_DROP_PREFIX.length) : null,
    });
    if (edit) onEdit(edit);
  }

  return (
    <div data-testid="arc-timeline-grid" className="flex flex-col gap-1">
      <span data-testid="arc-grid-live" aria-live="polite" className="sr-only">{announce}</span>
      {/* chapter ruler */}
      <div className="flex items-end gap-1 pl-24 text-[10px] text-neutral-400">
        {Array.from({ length: cols }, (_, i) => (
          <span key={i} className="flex-1 text-center tabular-nums">{i + 1}</span>
        ))}
      </div>
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="flex flex-col gap-1">
          {threads.map((th) => (
            <ThreadRow
              key={th.key}
              thread={th}
              threads={threads}
              placements={placements.filter((p) => p.thread === th.key)}
              chapterSpan={cols}
              editable={editable}
              grabbedId={grabbedId}
              setGrabbed={(id) => {
                setGrabbedId(id);
                if (id) {
                  const p = placements.find((x) => x.id === id);
                  setAnnounce(t('motif.arc.grabbed', {
                    name: p?.motif_name ?? '',
                    defaultValue: 'Grabbed {{name}}. Arrow keys move, Shift+Arrow resize, Enter to drop, Esc to release.',
                  }));
                } else {
                  setAnnounce('');
                }
              }}
              onEdit={onEdit}
              trackRef={th.key === threads[0]?.key ? trackRef : undefined}
            />
          ))}
        </div>
      </DndContext>
    </div>
  );
}

type ThreadRowProps = {
  thread: ArcThread;
  threads: ArcThread[];
  placements: ArcPlacement[];
  chapterSpan: number;
  editable: boolean;
  grabbedId: string | null;
  setGrabbed: (id: string | null) => void;
  onEdit?: (edit: ArcTimelineEdit) => void;
  trackRef?: React.MutableRefObject<HTMLDivElement | null>;
};

function ThreadRow({
  thread, threads, placements, chapterSpan, editable, grabbedId, setGrabbed, onEdit, trackRef,
}: ThreadRowProps) {
  const { setNodeRef, isOver } = useDroppable({ id: `${THREAD_DROP_PREFIX}${thread.key}` });
  return (
    <div className="flex items-stretch gap-1" data-testid={`arc-grid-thread-${thread.key}`}>
      <div className="flex w-24 shrink-0 items-center gap-1 text-xs text-neutral-600 dark:text-neutral-300">
        {thread.glyph ? <span aria-hidden>{thread.glyph}</span> : null}
        <span className="truncate">{thread.label}</span>
      </div>
      <div
        ref={(node) => { setNodeRef(node); if (trackRef) trackRef.current = node; }}
        className={`relative h-8 flex-1 rounded border ${isOver ? 'border-amber-400 bg-amber-50/40 dark:bg-amber-900/10' : 'border-neutral-200 dark:border-neutral-700'}`}
      >
        {/* chapter gridlines */}
        <div className="pointer-events-none absolute inset-0 flex">
          {Array.from({ length: chapterSpan }, (_, i) => (
            <span key={i} className="flex-1 border-r border-neutral-100 last:border-r-0 dark:border-neutral-800" />
          ))}
        </div>
        {placements.map((p) => (
          <PlacementCell
            key={p.id}
            placement={p}
            threads={threads}
            chapterSpan={chapterSpan}
            editable={editable}
            grabbed={grabbedId === p.id}
            setGrabbed={setGrabbed}
            onEdit={onEdit}
          />
        ))}
      </div>
    </div>
  );
}

type PlacementCellProps = {
  placement: ArcPlacement;
  threads: ArcThread[];
  chapterSpan: number;
  editable: boolean;
  grabbed: boolean;
  setGrabbed: (id: string | null) => void;
  onEdit?: (edit: ArcTimelineEdit) => void;
};

function PlacementCell({
  placement: p, threads, chapterSpan, editable, grabbed, setGrabbed, onEdit,
}: PlacementCellProps) {
  const { t } = useTranslation('composition');
  const { attributes, listeners, setNodeRef, transform } = useDraggable({ id: p.id, disabled: !editable });
  // dnd-kit injects its OWN aria-describedby (its keyboard-instructions region) — merge
  // it with ours so the screen-reader hears both the placement span AND the drag hint.
  const { 'aria-describedby': dndDescribedBy, ...restAttributes } = attributes as unknown as Record<string, unknown>;
  // percentage geometry (1-based chapters → 0-based offset).
  const left = ((p.span_start - 1) / chapterSpan) * 100;
  const width = ((p.span_end - p.span_start + 1) / chapterSpan) * 100;
  const threadLabel = threads.find((th) => th.key === p.thread)?.label ?? p.thread;
  const descId = `arc-desc-${p.id}`;
  const desc = t('motif.arc.placementDesc', {
    thread: threadLabel, from: p.span_start, to: p.span_end,
    defaultValue: '{{thread}} thread, chapters {{from}}-{{to}}',
  });

  function emitThreadShift(dir: -1 | 1) {
    const idx = threads.findIndex((th) => th.key === p.thread);
    const next = threads[idx + dir];
    if (next) onEdit?.({ type: 'move', placement_id: p.id, to_thread: next.key, delta_chapters: 0 });
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!editable || !onEdit) return;
    if (!grabbed) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setGrabbed(p.id); }
      return;
    }
    switch (e.key) {
      case 'Enter':
      case 'Escape':
        e.preventDefault(); setGrabbed(null); break;
      case 'ArrowLeft':
        e.preventDefault();
        onEdit(e.shiftKey
          ? { type: 'resize', placement_id: p.id, edge: 'end', delta: -1 }
          : { type: 'move', placement_id: p.id, to_thread: p.thread, delta_chapters: -1 });
        break;
      case 'ArrowRight':
        e.preventDefault();
        onEdit(e.shiftKey
          ? { type: 'resize', placement_id: p.id, edge: 'end', delta: 1 }
          : { type: 'move', placement_id: p.id, to_thread: p.thread, delta_chapters: 1 });
        break;
      case 'ArrowUp':
        e.preventDefault(); emitThreadShift(-1); break;
      case 'ArrowDown':
        e.preventDefault(); emitThreadShift(1); break;
      default:
        break;
    }
  }

  return (
    <>
      <span id={descId} className="sr-only">{desc}</span>
      <button
        type="button"
        ref={setNodeRef}
        data-testid={`arc-grid-placement-${p.id}`}
        {...restAttributes}
        {...(editable ? listeners : {})}
        aria-grabbed={grabbed}
        aria-describedby={[descId, dndDescribedBy].filter(Boolean).join(' ')}
        aria-label={`${p.motif_name} — ${desc}`}
        disabled={!editable}
        onKeyDown={onKeyDown}
        onBlur={() => { if (grabbed) setGrabbed(null); }}
        className={`absolute top-1 bottom-1 truncate rounded px-1 text-left text-[11px] ${grabbed ? 'ring-2 ring-amber-500' : ''} border border-amber-300 bg-amber-100 text-amber-900 dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-100`}
        style={{ left: `${left}%`, width: `${width}%`, transform: CSS.Translate.toString(transform) }}
      >
        {p.motif_name}
      </button>
    </>
  );
}
