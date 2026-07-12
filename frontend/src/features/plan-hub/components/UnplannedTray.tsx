// 24 PH21 — the "Unplanned chapters" tray: MANUSCRIPT chapters that no spec node covers.
// Drift made visible, never auto-planned.
//
// These have NO canvas node — that is precisely what makes them unplanned — so they cannot live on
// the graph. They dock as a collapsible tray under it, addressed by book-service `chapter_id`.
//
// NOT to be confused with `layout.unassigned` (spec chapters with no ARC), which DOES render on the
// canvas, in its own strip. Two directions of the same seam:
//     unplanned  = written, but not planned   (manuscript ∌ spec)  ← this file
//     unassigned = planned, but not filed     (spec, no arc lane)  ← the canvas strip
//
// `chapters === null` means the coverage diff could NOT be computed (the manuscript spine was
// unreadable). That renders as "unknown" — NEVER as an empty tray, which would say "nothing is
// unplanned" about something we simply do not know (absent ≠ zero).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { UnplannedChapter } from '../types';

export interface UnplannedTrayProps {
  /** THREE states (see PlanHubView.unplanned):
   *    undefined ⇒ still loading — render NOTHING (an "unknown" here would flash the degradation
   *                alarm on every cold open, while the overlay is merely in flight)
   *    null      ⇒ the server answered and omitted the key — render "unknown"
   *    []        ⇒ nothing unplanned — render nothing */
  chapters: UnplannedChapter[] | null | undefined;
  /** EXACT, even when the server capped the list. */
  total: number;
  /** Focus the chapter in the editor (the manuscript is where it actually lives). */
  onOpenChapter: (chapterId: string) => void;
}

export function UnplannedTray({ chapters, total, onOpenChapter }: UnplannedTrayProps) {
  const { t } = useTranslation('studio');
  const [open, setOpen] = useState(false);

  // Still loading ⇒ say nothing. This is NOT the same as "unknown": the server hasn't answered yet,
  // and claiming the manuscript could not be read while the request is still in flight would put a
  // false alarm on screen for the duration of every cold open.
  if (chapters === undefined) return null;
  // Nothing unplanned AND we know it → the tray has nothing to say. Stay out of the way.
  if (chapters !== null && chapters.length === 0) return null;

  const unknown = chapters === null;
  const capped = !unknown && total > chapters.length;

  return (
    <div
      data-testid="plan-hub-unplanned-tray"
      className="border-t bg-muted/30 text-xs"
    >
      <button
        type="button"
        data-testid="plan-hub-unplanned-toggle"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-accent/50"
      >
        <span className="text-muted-foreground">{open ? '▾' : '▸'}</span>
        {unknown ? (
          <span data-testid="plan-hub-unplanned-unknown" className="text-muted-foreground">
            {t(
              'planHub.node.unplannedUnknown',
              'Unplanned chapters: unknown (the manuscript could not be read)',
            )}
          </span>
        ) : (
          <span className="font-medium">
            {t('planHub.node.unplannedTray', 'Unplanned chapters')}{' '}
            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-amber-700">{total}</span>
          </span>
        )}
      </button>

      {open && !unknown && (
        <ul className="max-h-40 overflow-y-auto px-3 pb-2">
          {chapters.map((c) => (
            <li key={c.chapter_id} className="flex items-center gap-2 py-0.5">
              <span className="w-8 flex-shrink-0 text-right text-muted-foreground">
                {c.sort_order}
              </span>
              <button
                type="button"
                data-testid="plan-hub-unplanned-row"
                onClick={() => onOpenChapter(c.chapter_id)}
                className="min-w-0 flex-1 truncate text-left text-primary underline-offset-2 hover:underline"
                title={c.title}
              >
                {c.title || t('planHub.node.untitled', 'Untitled')}
              </button>
            </li>
          ))}
          {capped && (
            <li data-testid="plan-hub-unplanned-capped" className="py-1 text-muted-foreground">
              {t('planHub.node.unplannedCapped', '…and {{n}} more (list capped)', {
                n: total - chapters.length,
              })}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
