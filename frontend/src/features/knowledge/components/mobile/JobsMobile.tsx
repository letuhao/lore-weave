import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronDown, ChevronRight, Pause, Play, XCircle } from 'lucide-react';
import { Skeleton } from '@/components/shared';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { useExtractionJobs } from '../../hooks/useExtractionJobs';
import { TOUCH_TARGET_CLASS } from '../../lib/touchTarget';
import { knowledgeApi, type ExtractionJobWire } from '../../api';
import type { ExtractionJobStatus } from '../../types/projectState';

// K19f.3 — mobile Jobs list. Merges active + history from
// useExtractionJobs, sorts running/paused first, renders one card
// per job with inline expand for details. Actions are limited to
// pause/resume/cancel per the plan's "no retry with new settings —
// use desktop" rule.
//
// DROPPED from desktop ExtractionJobsTab:
//   - CostSummary card (read mobile → head to desktop for billing)
//   - Per-status sections (Running / Paused / Complete / Failed)
//     collapsed into a single sorted list
//   - JobDetailPanel slide-over (inline expand instead)
//   - JobLogsPanel (desktop only — verbose multi-line logs don't
//     fit a phone viewport)
//   - Retry-with-new-settings BuildGraphDialog (desktop-only per plan)
//
// Action failures surface as toasts. Success invalidates the
// knowledge-jobs query so the list refreshes (same pattern as
// JobDetailPanel's runAction).

const STATUS_SORT_ORDER: Record<ExtractionJobStatus, number> = {
  running: 0,
  paused: 1,
  pending: 2,
  failed: 3,
  cancelled: 4,
  complete: 5,
};

const STATUS_CLASS: Record<ExtractionJobStatus, string> = {
  pending: 'bg-muted text-muted-foreground',
  running: 'bg-blue-500/15 text-blue-700 dark:text-blue-300',
  paused: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  complete: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  failed: 'bg-destructive/15 text-destructive',
  cancelled: 'bg-muted text-muted-foreground',
};

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function progressPercent(job: ExtractionJobWire): number | null {
  if (!job.items_total || job.items_total <= 0) return null;
  return Math.round((job.items_processed / job.items_total) * 100);
}

export function JobsMobile() {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const { active, history, isLoading, activeError, historyError } =
    useExtractionJobs();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  // Tracks which job is currently mid-action so we can disable the
  // matching button and show its busy label. Maps job_id → action key.
  const [busy, setBusy] = useState<
    { jobId: string; action: 'pause' | 'resume' | 'cancel' } | null
  >(null);

  const sortedJobs = useMemo(() => {
    // Dedup by job_id — review-impl M1: during a running→complete
    // transition, the 2s active poll and 10s history poll can both
    // return the same job, and rendering `key={job.job_id}` twice
    // triggers React's duplicate-key warning + may drop one of the
    // cards. `active` wins because its status is fresher (2s vs 10s).
    const byId = new Map<string, ExtractionJobWire>();
    for (const j of active) byId.set(j.job_id, j);
    for (const j of history) if (!byId.has(j.job_id)) byId.set(j.job_id, j);
    return [...byId.values()].sort((a, b) => {
      const rank =
        STATUS_SORT_ORDER[a.status] - STATUS_SORT_ORDER[b.status];
      if (rank !== 0) return rank;
      // Within the same status, show most recent first.
      return (
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    });
  }, [active, history]);

  const anyError = activeError ?? historyError ?? null;

  const runAction = async (
    job: ExtractionJobWire,
    action: 'pause' | 'resume' | 'cancel',
  ) => {
    if (!accessToken) return;
    setBusy({ jobId: job.job_id, action });
    try {
      if (action === 'pause') {
        await knowledgeApi.pauseExtraction(job.project_id, accessToken);
      } else if (action === 'resume') {
        await knowledgeApi.resumeExtraction(job.project_id, accessToken);
      } else {
        await knowledgeApi.cancelExtraction(job.project_id, accessToken);
      }
      await queryClient.invalidateQueries({ queryKey: ['knowledge-jobs'] });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(
        t('mobile.jobs.actionFailed', {
          action: t(`mobile.jobs.actions.${action}`),
          error: msg,
        }),
      );
    } finally {
      setBusy(null);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="mobile-jobs-loading">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (anyError) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-[12px] text-destructive"
        data-testid="mobile-jobs-error"
      >
        {t('mobile.jobs.loadFailed', {
          error: anyError instanceof Error ? anyError.message : 'unknown error',
        })}
      </div>
    );
  }

  if (sortedJobs.length === 0) {
    return (
      <p
        className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
        data-testid="mobile-jobs-empty"
      >
        {t('mobile.jobs.empty')}
      </p>
    );
  }

  return (
    <ul className="space-y-2" data-testid="mobile-jobs-list">
      {sortedJobs.map((job) => {
        const isExpanded = expandedId === job.job_id;
        const pct = progressPercent(job);
        const canPause = job.status === 'running';
        const canResume = job.status === 'paused';
        const canCancel =
          job.status === 'running' || job.status === 'paused';
        const actionBusyHere = busy?.jobId === job.job_id ? busy.action : null;
        const projectLabel =
          job.project_name ??
          t('mobile.jobs.unknownProject', {
            id: job.project_id.slice(0, 8),
          });

        return (
          <li key={job.job_id}>
            <div
              className={cn(
                'rounded-lg border bg-card',
                isExpanded && 'ring-1 ring-primary/30',
              )}
              data-testid="mobile-job-card"
              data-job-id={job.job_id}
              data-status={job.status}
            >
              <button
                type="button"
                onClick={() =>
                  setExpandedId(isExpanded ? null : job.job_id)
                }
                aria-expanded={isExpanded ? 'true' : 'false'}
                className={cn(
                  TOUCH_TARGET_CLASS,
                  'flex w-full items-start gap-3 px-3 py-3 text-left',
                )}
                data-testid="mobile-job-toggle"
              >
                <span className="pt-0.5 text-muted-foreground">
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span
                    className="block truncate font-serif text-sm font-semibold"
                    title={projectLabel}
                  >
                    {projectLabel}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                    <span
                      className={cn(
                        'rounded px-1.5 py-0.5 uppercase tracking-wide',
                        STATUS_CLASS[job.status],
                      )}
                    >
                      {t(`mobile.jobs.status.${job.status}`)}
                    </span>
                    <span className="text-muted-foreground">
                      {formatDate(job.started_at)}
                    </span>
                  </span>
                  {pct != null &&
                    (job.status === 'running' || job.status === 'paused') && (
                      <span
                        className="mt-2 block h-1.5 w-full overflow-hidden rounded bg-muted"
                        data-testid="mobile-job-progress-track"
                      >
                        <span
                          className="block h-full bg-primary/70 transition-all"
                          style={{ width: `${pct}%` }}
                          data-testid="mobile-job-progress-fill"
                          data-progress-pct={pct}
                        />
                      </span>
                    )}
                </span>
              </button>

              {isExpanded && (
                <div
                  className="border-t px-3 py-3 text-[12px]"
                  data-testid="mobile-job-detail"
                >
                  <dl className="mb-3 grid grid-cols-[120px_1fr] gap-y-1 gap-x-2 text-[11px]">
                    <dt className="text-muted-foreground">
                      {t('mobile.jobs.detail.items')}
                    </dt>
                    <dd className="tabular-nums">
                      {job.items_processed.toLocaleString()}
                      {job.items_total != null && (
                        <> / {job.items_total.toLocaleString()}</>
                      )}
                    </dd>
                    <dt className="text-muted-foreground">
                      {t('mobile.jobs.detail.created')}
                    </dt>
                    <dd>{formatDate(job.created_at)}</dd>
                    {job.completed_at && (
                      <>
                        <dt className="text-muted-foreground">
                          {t('mobile.jobs.detail.completed')}
                        </dt>
                        <dd>{formatDate(job.completed_at)}</dd>
                      </>
                    )}
                  </dl>

                  {job.status === 'failed' && job.error_message && (
                    <div
                      className="mb-3 rounded border border-destructive/30 bg-destructive/5 p-2 text-[11px] text-destructive"
                      data-testid="mobile-job-error-message"
                    >
                      {job.error_message}
                    </div>
                  )}

                  {(canPause || canResume || canCancel) && (
                    <div className="flex flex-wrap justify-end gap-2">
                      {canPause && (
                        <button
                          type="button"
                          onClick={(ev) => {
                            ev.stopPropagation();
                            void runAction(job, 'pause');
                          }}
                          disabled={actionBusyHere !== null}
                          className={cn(
                            TOUCH_TARGET_CLASS,
                            'inline-flex items-center gap-1.5 rounded-md border px-3 text-[12px] font-medium transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50',
                          )}
                          data-testid="mobile-job-pause"
                        >
                          <Pause className="h-3.5 w-3.5" />
                          {actionBusyHere === 'pause'
                            ? t('mobile.jobs.actions.pausing')
                            : t('mobile.jobs.actions.pause')}
                        </button>
                      )}
                      {canResume && (
                        <button
                          type="button"
                          onClick={(ev) => {
                            ev.stopPropagation();
                            void runAction(job, 'resume');
                          }}
                          disabled={actionBusyHere !== null}
                          className={cn(
                            TOUCH_TARGET_CLASS,
                            'inline-flex items-center gap-1.5 rounded-md border px-3 text-[12px] font-medium transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50',
                          )}
                          data-testid="mobile-job-resume"
                        >
                          <Play className="h-3.5 w-3.5" />
                          {actionBusyHere === 'resume'
                            ? t('mobile.jobs.actions.resuming')
                            : t('mobile.jobs.actions.resume')}
                        </button>
                      )}
                      {canCancel && (
                        <button
                          type="button"
                          onClick={(ev) => {
                            ev.stopPropagation();
                            void runAction(job, 'cancel');
                          }}
                          disabled={actionBusyHere !== null}
                          className={cn(
                            TOUCH_TARGET_CLASS,
                            'inline-flex items-center gap-1.5 rounded-md border border-destructive/40 px-3 text-[12px] font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50',
                          )}
                          data-testid="mobile-job-cancel"
                        >
                          <XCircle className="h-3.5 w-3.5" />
                          {actionBusyHere === 'cancel'
                            ? t('mobile.jobs.actions.cancelling')
                            : t('mobile.jobs.actions.cancel')}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
