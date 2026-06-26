// W6 §5.4 — the MOBILE FALLBACK SKELETON for the arc-timeline (the frozen interface
// W10 implements against; the desktop edit-grid itself is P4/W10). A drag-grid is
// unusable on a phone → this is a vertical, per-thread LIST with explicit
// move/resize stepper buttons + a "+ place" affordance — NO dragging. Reads work on
// all sizes; this is the EDIT affordance for narrow widths. Render-only.
//
// This is the P1 deliverable for the mobile fallback contract (§5.4) — a working,
// accessible list. W10 wires it to a real arc-template + replaces the desktop grid.
import { useTranslation } from 'react-i18next';
import type { ArcTimelineContract, ArcPlacement } from '../arcTimelineContract';

export function ArcTimelineMobileList({ threads, placements, chapterSpan, onEdit, editGridEnabled }: ArcTimelineContract) {
  const { t } = useTranslation('composition');
  const byThread = (key: string): ArcPlacement[] =>
    placements.filter((p) => p.thread === key).sort((a, b) => a.span_start - b.span_start || a.ord - b.ord);

  return (
    <div data-testid="arc-timeline-mobile-list" className="flex flex-col gap-3 p-2">
      {!editGridEnabled && (
        <p data-testid="arc-timeline-mobile-notice" className="rounded border border-neutral-300 bg-neutral-50 p-2 text-[11px] text-neutral-500 dark:border-neutral-600 dark:bg-neutral-800">
          {t('motif.arc.mobileNotice', { defaultValue: 'The timeline grid is available on a larger screen — here you can edit it as a list.' })}
        </p>
      )}
      {threads.map((th) => (
        <section key={th.key} aria-label={th.label} className="flex flex-col gap-1">
          <header className="flex items-center justify-between">
            <span className="text-xs font-medium text-neutral-700 dark:text-neutral-200">
              {th.glyph ? `${th.glyph} ` : ''}{th.label}
            </span>
            <button
              type="button"
              data-testid={`arc-place-${th.key}`}
              className="rounded border border-amber-400 px-1.5 py-0.5 text-[11px] text-amber-700 dark:text-amber-300"
              onClick={() => onEdit?.({ type: 'place', thread: th.key, motif_code: '', span_start: 1, span_end: 1 })}
            >
              + {t('motif.arc.place', { defaultValue: 'place' })}
            </button>
          </header>
          {byThread(th.key).map((p) => (
            <div key={p.id} data-testid={`arc-row-${p.id}`} className="flex items-center justify-between gap-2 rounded border border-neutral-200 px-2 py-1 text-xs dark:border-neutral-700">
              <span className="min-w-0 truncate">
                <span className="font-medium">{p.motif_name}</span>
                <span className="ml-1 text-neutral-500">{t('motif.arc.chapters', { from: p.span_start, to: p.span_end, defaultValue: 'ch {{from}}-{{to}}' })}</span>
              </span>
              <div className="flex shrink-0 items-center gap-0.5">
                <StepBtn label={t('motif.arc.moveLeft', { defaultValue: 'Move earlier' })} testid={`arc-move-left-${p.id}`} disabled={p.span_start <= 1} onClick={() => onEdit?.({ type: 'move', placement_id: p.id, to_thread: p.thread, delta_chapters: -1 })}>◀</StepBtn>
                <StepBtn label={t('motif.arc.moveRight', { defaultValue: 'Move later' })} testid={`arc-move-right-${p.id}`} disabled={p.span_end >= chapterSpan} onClick={() => onEdit?.({ type: 'move', placement_id: p.id, to_thread: p.thread, delta_chapters: 1 })}>▶</StepBtn>
                <StepBtn label={t('motif.arc.grow', { defaultValue: 'Lengthen' })} testid={`arc-grow-${p.id}`} disabled={p.span_end >= chapterSpan} onClick={() => onEdit?.({ type: 'resize', placement_id: p.id, edge: 'end', delta: 1 })}>＋</StepBtn>
                <StepBtn label={t('motif.arc.shrink', { defaultValue: 'Shorten' })} testid={`arc-shrink-${p.id}`} disabled={p.span_end <= p.span_start} onClick={() => onEdit?.({ type: 'resize', placement_id: p.id, edge: 'end', delta: -1 })}>－</StepBtn>
                <StepBtn label={t('motif.arc.remove', { defaultValue: 'Remove' })} testid={`arc-remove-${p.id}`} onClick={() => onEdit?.({ type: 'remove', placement_id: p.id })}>✕</StepBtn>
              </div>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

function StepBtn({ label, testid, disabled, onClick, children }: { label: string; testid: string; disabled?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} data-testid={testid} disabled={disabled} className="rounded px-1 text-neutral-500 hover:bg-neutral-100 disabled:opacity-30 dark:hover:bg-neutral-800" onClick={onClick}>
      {children}
    </button>
  );
}
