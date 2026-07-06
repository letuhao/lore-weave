// #20_agent_mode.md §6 (Diff / review panel) + D10 (keyboard triage). The
// actual before/after prose reuses the SAME real diff data source as the
// classic compare route (booksApi.compareRevisions / RevisionDiff) — not a
// summary-only view (v1's biggest documented gap).
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { RevisionDiff } from '@/features/books/components/RevisionDiff';
import type { AuthoringRunStatus, CriticVerdict } from '@/features/composition/authoringRuns/types';
import { canReviewUnit, keyToUnitReviewAction } from '@/features/composition/authoringRuns/fsm';

export interface SelectedUnitDetail {
  unitIndex: number;
  chapterId: string;
  chapterLabel: string;
  status: string; // real AuthoringRunUnitStatus, or 'in_progress' (see UnitQueue)
  preRevisionId: string | null;
  postRevisionId: string | null;
  costUsd: string | null;
  errorMessage: string | null;
  criticVerdict: CriticVerdict | null;
  downstreamUnitIndexes: number[];
  notReached: boolean;
}

interface Props {
  bookId: string;
  runStatus: AuthoringRunStatus;
  unit: SelectedUnitDetail | null;
  onAccept: () => void;
  onReject: () => void;
  onNav: (direction: -1 | 1) => void;
  onOpenFullDiff: (chapterId: string, fromRevisionId: string, toRevisionId: string) => void;
  reviewBusy: boolean;
}

const SEV_LABEL_KEY: Record<string, string> = { ok: 'ok', warn: 'warn', severe: 'severe' };

export function DiffReviewPanel({ bookId, runStatus, unit, onAccept, onReject, onNav, onOpenFullDiff, reviewBusy }: Props) {
  const { t } = useTranslation('composition');
  const { accessToken } = useAuth();
  const [detailOpen, setDetailOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-focus so keyboard triage works as soon as a unit is picked, without
  // requiring an extra click — D10 says "with the diff/review panel focused".
  useEffect(() => {
    if (unit) containerRef.current?.focus();
  }, [unit?.unitIndex]);

  const canCompare = !!unit?.preRevisionId && !!unit?.postRevisionId;
  const compareQuery = useQuery({
    queryKey: ['authoring-unit-diff', bookId, unit?.chapterId, unit?.preRevisionId, unit?.postRevisionId],
    queryFn: () => booksApi.compareRevisions(accessToken!, bookId, unit!.chapterId, unit!.preRevisionId!, unit!.postRevisionId!),
    enabled: !!accessToken && !!unit && canCompare,
  });

  if (!unit) {
    return (
      <div data-testid="agent-mode-diff-panel-empty" className="rounded-md border p-3 text-xs text-muted-foreground">
        {t('authoringRun.diff.notDrafted', { defaultValue: 'Not drafted yet — nothing to review.' })}
      </div>
    );
  }

  const reviewable = canReviewUnit(runStatus, unit.status as never);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const action = keyToUnitReviewAction(e.key);
    if (!action) return;
    e.preventDefault();
    if (action === 'next') return onNav(1);
    if (action === 'prev') return onNav(-1);
    if (!reviewable || reviewBusy) return; // no-op — D10: never error on an illegal state
    if (action === 'accept') onAccept();
    if (action === 'reject') onReject();
  };

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      role="group"
      aria-label={t('authoringRun.diff.title', { defaultValue: 'Draft review' })}
      onKeyDown={handleKeyDown}
      data-testid="agent-mode-diff-panel"
      className="rounded-md border p-3 outline-none focus:ring-1 focus:ring-accent"
    >
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-xs font-semibold">
          {unit.chapterLabel} — {t('authoringRun.diff.title', { defaultValue: 'Draft review' })}
        </h3>
        <div className="ml-auto flex gap-1.5">
          <button type="button" data-testid="agent-mode-diff-prev" onClick={() => onNav(-1)} className="rounded-md border px-2 py-0.5 text-[10.5px] hover:bg-secondary">
            {t('authoringRun.diff.prev', { defaultValue: '← Prev' })}
          </button>
          <button type="button" data-testid="agent-mode-diff-next" onClick={() => onNav(1)} className="rounded-md border px-2 py-0.5 text-[10.5px] hover:bg-secondary">
            {t('authoringRun.diff.next', { defaultValue: 'Next →' })}
          </button>
        </div>
      </div>

      {unit.notReached && (
        <p className="text-xs text-muted-foreground">{t('authoringRun.diff.notReached', { defaultValue: 'Run halted before reaching this chapter.' })}</p>
      )}
      {unit.status === 'failed' && unit.errorMessage && (
        <div className="rounded-md border border-destructive bg-destructive/10 p-2 font-mono text-[11px]">
          {t('authoringRun.diff.failedUnit', { defaultValue: 'This unit failed:' })} {unit.errorMessage}
        </div>
      )}
      {!unit.notReached && (unit.status === 'pending') && (
        <p className="text-xs text-muted-foreground">{t('authoringRun.diff.notDrafted', { defaultValue: 'Not drafted yet — nothing to review.' })}</p>
      )}

      {(unit.status === 'drafted' || unit.status === 'accepted' || unit.status === 'rejected' || unit.status === 'in_progress') && (
        <>
          {compareQuery.isLoading && <p className="text-xs text-muted-foreground">…</p>}
          {compareQuery.data && (
            <div data-testid="agent-mode-diff-body" className="mb-2">
              <RevisionDiff diff={compareQuery.data.diff} mode="inline" />
            </div>
          )}
          {!canCompare && (
            <p className="text-xs text-muted-foreground">{t('authoringRun.diff.notDrafted', { defaultValue: 'Not drafted yet — nothing to review.' })}</p>
          )}

          {canCompare && (
            <div className="mb-2 flex items-center gap-2 text-[10.5px] text-muted-foreground">
              <span className="rounded bg-secondary px-1.5 py-0.5 font-mono">{unit.preRevisionId!.slice(0, 8)}…</span>
              <span>→</span>
              <span className="rounded bg-secondary px-1.5 py-0.5 font-mono">{unit.postRevisionId!.slice(0, 8)}…</span>
              <button
                type="button"
                data-testid="agent-mode-open-full-diff"
                onClick={() => onOpenFullDiff(unit.chapterId, unit.preRevisionId!, unit.postRevisionId!)}
                className="text-accent-foreground underline"
              >
                {t('authoringRun.diff.openFullDiff', { defaultValue: 'Open full editor diff' })}
              </button>
            </div>
          )}

          {unit.criticVerdict && (
            <div className="rounded-md border bg-secondary/40 p-2" data-testid="agent-mode-critic-verdict">
              <div className="mb-1 flex items-center gap-2">
                <span className="text-[10px] font-bold uppercase">{t(`authoringRun.diff.sev.${SEV_LABEL_KEY[unit.criticVerdict.severity]}`, { defaultValue: unit.criticVerdict.severity })}</span>
                <span className="ml-auto font-mono text-[10px] text-muted-foreground">${unit.criticVerdict.cost_usd}</span>
              </div>
              <p className="text-xs">{unit.criticVerdict.summary}</p>
              {unit.criticVerdict.detail && (
                <>
                  <button type="button" data-testid="agent-mode-verdict-toggle" onClick={() => setDetailOpen((v) => !v)} className="mt-1 text-[10px] text-accent-foreground underline">
                    {detailOpen
                      ? t('authoringRun.diff.verdictHide', { defaultValue: 'Hide detail ▴' })
                      : t('authoringRun.diff.verdictShow', { defaultValue: 'Show detail ▾' })}
                  </button>
                  {detailOpen && (
                    <pre data-testid="agent-mode-verdict-detail" className="mt-1 overflow-x-auto rounded bg-background p-1.5 text-[10px]">
                      {JSON.stringify(unit.criticVerdict.detail, null, 2)}
                    </pre>
                  )}
                </>
              )}
            </div>
          )}

          {unit.downstreamUnitIndexes.length > 0 && (
            <div data-testid="agent-mode-cascade-warning" className="mt-2 rounded-md border border-warning bg-warning/10 p-2 text-[11px]">
              {t('authoringRun.diff.cascadeWarning', {
                count: unit.downstreamUnitIndexes.length,
                chapters: unit.downstreamUnitIndexes.map((i) => `Ch.${i + 1}`).join(', '),
                defaultValue: '{{count}} downstream unit(s) already drafted/accepted ({{chapters}}) — this is advisory only; rejecting this unit does NOT auto-revert them.',
              })}
            </div>
          )}

          {/* D8 — hard-disable outside reviewable states/unit status, with an inline reason (never a silently-failed request). */}
          {(unit.status === 'accepted' || unit.status === 'rejected') ? (
            <p className="mt-2 text-[11px] italic text-muted-foreground" data-testid="agent-mode-already-reviewed">
              {t('authoringRun.diff.alreadyReviewed', { status: unit.status, defaultValue: 'Already reviewed — currently {{status}}.' })}
            </p>
          ) : !reviewable ? (
            <p className="mt-2 text-[11px] text-warning" data-testid="agent-mode-review-blocked">
              {t('authoringRun.diff.blockedReview', {
                status: runStatus,
                defaultValue:
                  'Accept/Reject blocked while the run is {{status}} — the backend only allows review once the run has stopped (report_ready / failed / paused). Pause the run to review this chapter now.',
              })}
            </p>
          ) : (
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                data-testid="agent-mode-accept-unit"
                disabled={reviewBusy}
                onClick={onAccept}
                className="rounded-md border border-primary bg-primary/10 px-3 py-1 text-xs font-semibold text-primary hover:bg-primary/20 disabled:opacity-40"
              >
                {t('authoringRun.diff.accept', { defaultValue: 'Accept' })}
              </button>
              <button
                type="button"
                data-testid="agent-mode-reject-unit"
                disabled={reviewBusy}
                onClick={onReject}
                className="rounded-md border border-destructive bg-destructive/10 px-3 py-1 text-xs font-semibold text-destructive hover:bg-destructive/20 disabled:opacity-40"
              >
                {t('authoringRun.diff.reject', { defaultValue: 'Reject' })}
              </button>
            </div>
          )}
          <p className="mt-2 text-[10px] text-muted-foreground">
            {t('authoringRun.diff.keyboardHint', { defaultValue: 'Keyboard: a=accept · r=reject · ←/→ or p/n = prev/next unit' })}
          </p>
        </>
      )}
    </div>
  );
}
