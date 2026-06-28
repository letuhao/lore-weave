// W10 §5.4 — the responsive arc-timeline EDITOR shell. Wires useArcTimeline (the edit
// controller) and swaps the surface by viewport: the desktop drag-grid (≥ md) vs the
// mobile stepper-list (< md). Both bind the SAME ArcTimelineContract, so edits flow
// through one reducer + one debounced persist. Read-only for a non-owned arc (the
// "adopt to edit" affordance) — onEdit is withheld so both surfaces render inert.
import { useTranslation } from 'react-i18next';
import { useIsMobile } from '../../../knowledge/hooks/useIsMobile';
import { useArcTimeline } from '../hooks/useArcTimeline';
import type { ArcTimelineContract } from '../arcTimelineContract';
import { ArcTimelineGrid } from './ArcTimelineGrid';
import { ArcTimelineMobileList } from './ArcTimelineMobileList';

export function ArcTimelineEditor({ arcId, token }: { arcId: string | null; token: string | null }) {
  const { t } = useTranslation('composition');
  const isMobile = useIsMobile();
  const {
    arc, isLoading, isError, threads, placements, chapterSpan, canEdit, onEdit, saving, saveError,
  } = useArcTimeline(arcId, token);

  if (!arcId) return null;
  if (isLoading) {
    return <div data-testid="arc-timeline-loading" className="p-3 text-xs text-neutral-400">{t('motif.arc.loading', { defaultValue: 'Loading timeline…' })}</div>;
  }
  if (isError || !arc) {
    return <div data-testid="arc-timeline-error" role="alert" className="p-3 text-xs text-destructive">{t('motif.arc.loadError', { defaultValue: 'Could not load this arc timeline.' })}</div>;
  }

  const contract: ArcTimelineContract = {
    threads,
    placements,
    chapterSpan,
    // read-only when not the owner → withhold onEdit so the grid/list render inert.
    onEdit: canEdit ? onEdit : undefined,
    // the edit-grid is allowed only on desktop AND when the caller may edit.
    editGridEnabled: !isMobile && canEdit,
  };

  const empty = threads.length === 0 && placements.length === 0;

  return (
    <div data-testid="arc-timeline-editor" className="flex flex-col gap-2 p-2">
      <header className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-medium">{arc.name}</h3>
          <p className="text-[11px] text-neutral-500">
            {t('motif.arc.chapterCount', { count: chapterSpan, defaultValue: '{{count}} chapters' })}
          </p>
        </div>
        <SaveStatus saving={saving} saveError={saveError} canEdit={canEdit} />
      </header>

      {!canEdit && (
        <p data-testid="arc-timeline-readonly" className="rounded border border-neutral-300 bg-neutral-50 p-2 text-[11px] text-neutral-500 dark:border-neutral-600 dark:bg-neutral-800">
          {t('motif.arc.readonly', { defaultValue: 'This arc is read-only. Adopt it to your library to edit the timeline.' })}
        </p>
      )}

      {empty ? (
        <p data-testid="arc-timeline-empty" className="p-3 text-xs text-neutral-400">
          {t('motif.arc.empty', { defaultValue: 'This arc has no threads or placements yet.' })}
        </p>
      ) : isMobile ? (
        <ArcTimelineMobileList {...contract} />
      ) : (
        <ArcTimelineGrid {...contract} />
      )}
    </div>
  );
}

function SaveStatus({ saving, saveError, canEdit }: { saving: boolean; saveError: 'conflict' | 'error' | null; canEdit: boolean }) {
  const { t } = useTranslation('composition');
  if (!canEdit) return null;
  if (saveError === 'conflict') {
    return <span data-testid="arc-save-conflict" className="text-[11px] text-amber-600" role="status">{t('motif.arc.saveConflict', { defaultValue: 'Reloaded — this arc changed elsewhere.' })}</span>;
  }
  if (saveError === 'error') {
    return <span data-testid="arc-save-error" className="text-[11px] text-destructive" role="status">{t('motif.arc.saveError', { defaultValue: "Couldn't save — retrying on next edit." })}</span>;
  }
  if (saving) {
    return <span data-testid="arc-save-saving" className="text-[11px] text-neutral-400" role="status">{t('motif.arc.saving', { defaultValue: 'Saving…' })}</span>;
  }
  return <span data-testid="arc-save-idle" className="text-[11px] text-neutral-400" role="status">{t('motif.arc.saved', { defaultValue: 'Saved' })}</span>;
}
