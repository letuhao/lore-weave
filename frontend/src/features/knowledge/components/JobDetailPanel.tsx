import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import { knowledgeApi, type ExtractionJobWire } from '../api';
import { useJobProgressRate } from '../hooks/useJobProgressRate';
import { JobProgressBar } from './JobProgressBar';
import { JobLogsPanel } from './JobLogsPanel';

// K19b.3 — slide-over panel for inspecting a single extraction job.
// Opens when a row in ExtractionJobsTab is clicked. Pure read-only for
// terminal jobs; for active/paused jobs, surfaces Pause/Resume/Cancel.
// For failed jobs specifically (NOT cancelled — review-design R3),
// exposes a Retry CTA that the parent wires to BuildGraphDialog with
// initial values.
//
// Data source: the clicked ExtractionJobWire is passed in directly.
// For active jobs the parent's `useExtractionJobs` hook polls every
// 2s, and the React Query cache is the same instance the panel reads
// from its parent — so progress updates flow in without the panel
// maintaining its own query.

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  job: ExtractionJobWire | null;
  /** K19b.5: only wired for failed jobs (R3). When the user clicks
   *  "Retry with different settings" the parent opens BuildGraphDialog
   *  with `initialValues` derived from the failed job, and typically
   *  closes this panel (R2). */
  onRetryClick?: (job: ExtractionJobWire) => void;
}

const ACTIVE_STATUSES: ReadonlySet<ExtractionJobWire['status']> = new Set([
  'running',
  'paused',
  'pending',
]);

function formatCost(raw: string): string {
  const n = Number(raw);
  if (!Number.isFinite(n)) return `$${raw}`;
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(n);
}

const LONG_DATE_FORMATTER = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

function formatLongDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : LONG_DATE_FORMATTER.format(d);
}

function MetadataRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[100px_minmax(0,1fr)] gap-3 text-[12px]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-foreground">{value}</dd>
    </div>
  );
}

export function JobDetailPanel({ open, onOpenChange, job, onRetryClick }: Props) {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [actionBusy, setActionBusy] = useState<
    null | 'pause' | 'resume' | 'cancel'
  >(null);

  // Note: hook called unconditionally (React rules of hooks). It
  // internally returns null ETA when job is null / non-running.
  const { minutesRemaining } = useJobProgressRate(job);

  const runAction = async (
    key: 'pause' | 'resume' | 'cancel',
    op: () => Promise<unknown>,
    labelKey: string,
  ) => {
    if (!job || !accessToken) return;
    setActionBusy(key);
    try {
      await op();
      // Invalidate both active + history queries since cancel moves
      // a row from active → history (status becomes 'cancelled').
      await queryClient.invalidateQueries({ queryKey: ['knowledge-jobs'] });
      onOpenChange(false);
    } catch (err) {
      const label = t(labelKey);
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(t('jobs.detail.actionFailed', { label, error: msg }));
    } finally {
      setActionBusy(null);
    }
  };

  const handleRetry = () => {
    if (!job) return;
    onRetryClick?.(job);
  };

  if (!job) {
    // Dialog stays mounted so the close animation can play; render
    // nothing meaningful when the job prop is nulled out by the parent.
    return null;
  }

  const isActive = ACTIVE_STATUSES.has(job.status);
  const isFailed = job.status === 'failed';
  const canRetry = isFailed && !!onRetryClick;
  const projectLabel =
    job.project_name ??
    t('jobs.row.unknownProject', { id: job.project_id.slice(0, 8) });

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content
          className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col overflow-y-auto border-l bg-background shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right"
          data-testid="job-detail-panel"
        >
          <div className="flex items-start justify-between border-b px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="truncate font-serif text-base font-semibold">
                {t('jobs.detail.title')}
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 truncate text-[12px] text-muted-foreground">
                {projectLabel}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                className="rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground"
                aria-label={t('jobs.detail.close')}
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <div className="flex-1 space-y-5 px-5 py-4">
            {/* Progress */}
            <section className="space-y-2">
              <JobProgressBar
                status={job.status}
                itemsProcessed={job.items_processed}
                itemsTotal={job.items_total}
                costSpentUsd={job.cost_spent_usd}
                maxSpendUsd={job.max_spend_usd}
              />
              <p className="text-[12px] text-muted-foreground">
                {t('jobs.detail.itemsProgress', {
                  processed: job.items_processed,
                  total: job.items_total ?? '—',
                })}
              </p>
              {minutesRemaining != null && (
                <p
                  className="text-[12px] text-muted-foreground"
                  data-testid="job-detail-eta"
                >
                  {t('jobs.detail.eta', {
                    minutes: Math.max(1, Math.round(minutesRemaining)),
                  })}
                </p>
              )}
            </section>

            {/* Metadata */}
            <section>
              <dl className="space-y-1.5">
                <MetadataRow
                  label={t('jobs.detail.status')}
                  value={
                    <span
                      className="inline-block rounded-md bg-muted px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide"
                      data-testid="job-detail-status"
                    >
                      {job.status}
                    </span>
                  }
                />
                <MetadataRow label={t('jobs.detail.scope')} value={job.scope} />
                <MetadataRow
                  label={t('jobs.detail.llmModel')}
                  value={job.llm_model}
                />
                <MetadataRow
                  label={t('jobs.detail.embeddingModel')}
                  value={job.embedding_model}
                />
                <MetadataRow
                  label={t('jobs.detail.maxSpend')}
                  value={
                    job.max_spend_usd ? formatCost(job.max_spend_usd) : '—'
                  }
                />
                <MetadataRow
                  label={t('jobs.detail.startedAt')}
                  value={formatLongDate(job.started_at)}
                />
                <MetadataRow
                  label={t('jobs.detail.completedAt')}
                  value={formatLongDate(job.completed_at)}
                />
              </dl>
            </section>

            {/* Error (failed only) */}
            {isFailed && job.error_message && (
              <section
                className="rounded-md border border-destructive/40 bg-destructive/5 p-3"
                data-testid="job-detail-error"
              >
                <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-destructive">
                  {t('jobs.detail.errorTitle')}
                </p>
                <pre className="whitespace-pre-wrap break-words text-[12px] text-destructive/90">
                  {job.error_message}
                </pre>
              </section>
            )}

            {/* K19b.8 — job lifecycle logs. Collapsed by default.
                C3: pass jobStatus so the hook can enable 5s
                refetchInterval while the job is still running and
                stop polling on terminal states. */}
            <JobLogsPanel jobId={job.job_id} jobStatus={job.status} />
          </div>

          {/* Actions footer */}
          {(isActive || canRetry) && (
            <div className="flex flex-wrap gap-2 border-t bg-muted/30 px-5 py-3">
              {isActive && job.status === 'running' && (
                <button
                  onClick={() =>
                    runAction(
                      'pause',
                      () => knowledgeApi.pauseExtraction(job.project_id, accessToken!),
                      'jobs.detail.actions.pause',
                    )
                  }
                  disabled={actionBusy !== null}
                  className={cn(
                    'rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50',
                  )}
                  data-testid="job-detail-pause"
                >
                  {t('jobs.detail.actions.pause')}
                </button>
              )}
              {isActive && job.status === 'paused' && (
                <button
                  onClick={() =>
                    runAction(
                      'resume',
                      () => knowledgeApi.resumeExtraction(job.project_id, accessToken!),
                      'jobs.detail.actions.resume',
                    )
                  }
                  disabled={actionBusy !== null}
                  className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid="job-detail-resume"
                >
                  {t('jobs.detail.actions.resume')}
                </button>
              )}
              {isActive && (
                <button
                  onClick={() =>
                    runAction(
                      'cancel',
                      () => knowledgeApi.cancelExtraction(job.project_id, accessToken!),
                      'jobs.detail.actions.cancel',
                    )
                  }
                  disabled={actionBusy !== null}
                  className="rounded-md border border-destructive/30 px-3 py-1.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid="job-detail-cancel"
                >
                  {t('jobs.detail.actions.cancel')}
                </button>
              )}
              {canRetry && (
                <button
                  onClick={handleRetry}
                  className="ml-auto rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                  data-testid="job-detail-retry"
                >
                  {t('jobs.retry.button')}
                </button>
              )}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
