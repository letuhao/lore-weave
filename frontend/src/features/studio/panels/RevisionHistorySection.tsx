// #16 Phase 1, task 1.3 — Revision History section for the Studio EditorPanel. Ports the
// presentational shape of the legacy `components/editor/RevisionHistory.tsx` (list + restore),
// driven by `useRevisionHistory` instead of the legacy component's own local state. Self-contained
// (DOCK-10 hoist ownership / CLAUDE.md "no prop-drilling middlemen"): reads the Tier-4 hoist and
// bookId itself, exactly like the sibling `SceneRail` does, so `EditorPanel.tsx` only needs a
// single `<RevisionHistorySection />` tag — no new state/props to thread through.
//
// Deliberately NOT ported from the legacy component (out of scope for 1.3, see spec #16 Phase 1
// row + PR brief): the full-screen revision PREVIEW overlay and the separate Compare route
// (`useRevisionCompare` / `/compare`) — both are additive UX, not data-safety gaps, and compare in
// particular is its own concern (a distinct hook/route) rather than part of "list + restore".
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Clock, RotateCcw, ChevronRight } from 'lucide-react';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { Skeleton } from '@/components/shared/Skeleton';
import { cn } from '@/lib/utils';
import { useStudioHost } from '../host/StudioHostProvider';
import { useManuscriptUnit } from '../manuscript/unit/ManuscriptUnitProvider';
import { useRevisionHistory, type Revision } from '../manuscript/unit/useRevisionHistory';

export function RevisionHistorySection() {
  const { t } = useTranslation('studio');
  const { bookId } = useStudioHost();
  const unit = useManuscriptUnit();
  const chapterId = unit?.state.chapterId ?? null;
  const rev = useRevisionHistory(unit, bookId);
  const [open, setOpen] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<Revision | null>(null);

  // No chapter loaded — nothing to show a history for (mirrors EditorPanel's own empty-state gate).
  if (!chapterId) return null;

  const handleRestoreClick = (r: Revision) => {
    // Check the G7 guard up front so a dirty hoist shows the blocked banner immediately instead
    // of popping a confirm dialog the restore would just refuse anyway.
    if (unit?.isChapterDirty(chapterId)) {
      void rev.restore(r.revision_id);
      return;
    }
    setConfirmTarget(r);
  };

  const handleConfirmRestore = () => {
    if (!confirmTarget) return;
    const target = confirmTarget;
    setConfirmTarget(null);
    void rev.restore(target.revision_id);
  };

  return (
    <div
      data-testid="studio-revision-history"
      className={cn(
        'flex h-full flex-shrink-0 flex-col border-l bg-card/50 transition-[width]',
        open ? 'w-72' : 'w-8',
      )}
    >
      <button
        type="button"
        data-testid="studio-revision-history-toggle"
        onClick={() => setOpen((o) => !o)}
        title={t('revision.header', { count: rev.total, defaultValue: 'Revision history' })}
        className="flex h-7 flex-shrink-0 items-center gap-1 border-b px-1.5 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        <Clock className="h-3.5 w-3.5" />
        {open && <span className="flex-1 text-left">{t('revision.header', { count: rev.total, defaultValue: 'History' })}</span>}
        <ChevronRight className={cn('h-3 w-3 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="flex min-h-0 flex-1 flex-col">
          {rev.blocked && (
            <div data-testid="studio-revision-history-blocked" className="border-b bg-warning/10 px-2 py-1.5 text-[10px] text-warning">
              {t('revision.blocked_dirty', {
                defaultValue: 'You have unsaved changes. Save or discard them before restoring a revision.',
              })}
            </div>
          )}
          {rev.error && (
            <div className="border-b px-2 py-1.5 text-[10px] text-destructive">{rev.error}</div>
          )}

          {rev.loading ? (
            <div className="space-y-2 p-3">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-3/4" />
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto">
              {rev.revisions.length === 0 && (
                <p className="p-3 text-[10px] italic text-muted-foreground">
                  {t('revision.empty', { defaultValue: 'No revisions yet.' })}
                </p>
              )}
              {rev.revisions.map((r, i) => (
                <div key={r.revision_id} data-testid="studio-revision-history-item" className="border-b px-2 py-2 text-[10px] hover:bg-secondary/40">
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-medium">
                      {i === 0 ? t('revision.current', { defaultValue: 'Current' }) : `v${rev.revisions.length - i}`}
                    </span>
                    {i > 0 && (
                      <button
                        type="button"
                        data-testid="studio-revision-history-restore"
                        onClick={() => handleRestoreClick(r)}
                        disabled={rev.restoringId === r.revision_id}
                        className="inline-flex items-center gap-0.5 text-primary hover:underline disabled:opacity-40"
                      >
                        <RotateCcw className="h-2.5 w-2.5" />
                        {t('revision.restore', { defaultValue: 'Restore' })}
                      </button>
                    )}
                  </div>
                  {r.message && <p className="mt-0.5 text-muted-foreground">{r.message}</p>}
                  <p className="mt-0.5 text-muted-foreground">{new Date(r.created_at).toLocaleString()}</p>
                </div>
              ))}
              {rev.hasMore && (
                <button
                  type="button"
                  onClick={() => void rev.loadMore()}
                  disabled={rev.loadingMore}
                  className="w-full py-1.5 text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  {rev.loadingMore
                    ? t('revision.loading_more', { defaultValue: 'Loading…' })
                    : t('revision.load_more', { defaultValue: 'Load more' })}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmTarget}
        onOpenChange={(o) => { if (!o) setConfirmTarget(null); }}
        title={t('revision.confirm_title', { defaultValue: 'Restore this revision?' })}
        description={t('revision.confirm_desc', {
          defaultValue: 'The current draft will be replaced with this revision. This cannot be undone.',
        })}
        confirmLabel={t('revision.restore', { defaultValue: 'Restore' })}
        variant="destructive"
        onConfirm={handleConfirmRestore}
      />
    </div>
  );
}
