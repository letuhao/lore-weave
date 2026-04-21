import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import { useExtractionJobs } from '../hooks/useExtractionJobs';
import { knowledgeApi, type ExtractionJobWire } from '../api';
import { JobProgressBar } from './JobProgressBar';
import { JobDetailPanel } from './JobDetailPanel';
import {
  BuildGraphDialog,
  type BuildGraphInitialValues,
} from './BuildGraphDialog';

// K19b.2 — cross-project Jobs tab. Consumes `useExtractionJobs` for
// dual active/history polling and renders 4 sections matching the
// plan's layout (Running / Paused / Complete / Failed). `pending`
// and `cancelled` merge into their nearest-UX cousins: pending → Running
// (queued but not yet dispatched — same actionable state from the
// user's view), cancelled → Failed (both terminal non-success).
//
// Rows are non-interactive in this cycle. K19b.3 will add the
// click-to-open-detail slide-over; until then the tab is a pure
// read-only status monitor, which matches what users need while
// extraction is running in the background.

const COMPLETE_VISIBLE_LIMIT = 10;

// review-impl L3: hoisted to module scope so JobRow doesn't allocate a
// fresh formatter on every render. Matches the USD_FORMATTER pattern
// in JobProgressBar.
const SHORT_DATE_FORMATTER = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

type SectionProps = {
  title: string;
  emptyMessage: string;
  jobs: ExtractionJobWire[];
  onSelect: (jobId: string) => void;
  /** Collapsed by default via the native <details> element. */
  collapsedByDefault?: boolean;
  /** Highlight the section border/background when non-empty — used
   *  for Failed so bad news catches the eye without being loud on an
   *  empty dashboard. */
  highlightWhenNonEmpty?: boolean;
};

function Section({
  title,
  emptyMessage,
  jobs,
  onSelect,
  collapsedByDefault,
  highlightWhenNonEmpty,
}: SectionProps) {
  const shouldHighlight = !!highlightWhenNonEmpty && jobs.length > 0;

  return (
    <details
      open={!collapsedByDefault}
      className={cn(
        'group rounded-lg border bg-card transition-colors',
        shouldHighlight && 'border-destructive/40 bg-destructive/5',
      )}
    >
      <summary className="cursor-pointer select-none px-4 py-3 text-[13px] font-medium">
        <span className="mr-2 inline-block w-3 text-muted-foreground transition-transform group-open:rotate-90">
          ▸
        </span>
        {title}
        <span className="ml-2 text-[11px] font-normal text-muted-foreground">
          ({jobs.length})
        </span>
      </summary>
      <div className="space-y-2 border-t px-4 py-3">
        {jobs.length === 0 ? (
          <p className="text-[12px] text-muted-foreground">{emptyMessage}</p>
        ) : (
          jobs.map((j) => <JobRow key={j.job_id} job={j} onSelect={onSelect} />)
        )}
      </div>
    </details>
  );
}

function JobRow({
  job,
  onSelect,
}: {
  job: ExtractionJobWire;
  onSelect: (jobId: string) => void;
}) {
  const { t } = useTranslation('knowledge');
  const nameFallback = t('jobs.row.unknownProject', {
    id: job.project_id.slice(0, 8),
  });
  const name = job.project_name ?? nameFallback;
  // Prefer completed_at for terminal rows, started_at for active,
  // created_at as last resort (pending that never started).
  const isTerminal = ['complete', 'failed', 'cancelled'].includes(job.status);
  const when = isTerminal
    ? job.completed_at ?? job.created_at
    : job.started_at ?? job.created_at;
  const whenLabel = formatShortDate(when);
  const timestampKey = isTerminal ? 'jobs.row.completed' : 'jobs.row.started';

  // K19b.3: row opens JobDetailPanel on click or Enter/Space.
  // role="button" + tabIndex=0 + onKeyDown is the WAI-ARIA pattern
  // for turning a <div> into a focusable activatable element.
  const handleKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect(job.job_id);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(job.job_id)}
      onKeyDown={handleKey}
      className="grid cursor-pointer grid-cols-[minmax(0,1fr)_200px] items-center gap-3 rounded-md px-2 py-1 text-[13px] transition-colors hover:bg-muted/50 focus:bg-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      data-testid="job-row"
      data-job-id={job.job_id}
    >
      <div className="min-w-0">
        <div className="truncate font-medium" title={name}>
          {name}
        </div>
        <div className="text-[11px] text-muted-foreground">
          {t(timestampKey, { when: whenLabel })}
        </div>
      </div>
      <JobProgressBar
        status={job.status}
        itemsProcessed={job.items_processed}
        itemsTotal={job.items_total}
        costSpentUsd={job.cost_spent_usd}
        maxSpendUsd={job.max_spend_usd}
      />
    </div>
  );
}

function ErrorBanner({
  messageKey,
  error,
}: {
  messageKey: string;
  error: Error;
}) {
  const { t } = useTranslation('knowledge');
  return (
    <div
      role="alert"
      className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-2 text-[12px] text-destructive"
      data-testid="jobs-error-banner"
    >
      <span className="font-medium">{t(messageKey)}</span>
      <span className="ml-2 text-destructive/80">{error.message}</span>
    </div>
  );
}

// Minimal date formatter — ISO timestamp → "Apr 19, 12:00". i18n-safe
// via `Intl.DateTimeFormat` with undefined locale (picks browser
// default). K19b.7 may later swap to a relative formatter ("2h ago").
function formatShortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return SHORT_DATE_FORMATTER.format(d);
}

/** K19b.5 retry state — consolidated per review-design R1. */
interface RetryIntent {
  projectId: string;
  initialValues: BuildGraphInitialValues;
}

function retryInitialsFromJob(job: ExtractionJobWire): BuildGraphInitialValues {
  return {
    scope: job.scope,
    llmModel: job.llm_model,
    embeddingModel: job.embedding_model,
    maxSpend: job.max_spend_usd ?? '',
  };
}

export function ExtractionJobsTab() {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();
  const { active, history, isLoading, activeError, historyError } =
    useExtractionJobs();

  // K19b.3: which job is the detail panel looking at.
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  // K19b.5: retry flow — populated on panel's Retry click.
  const [retryIntent, setRetryIntent] = useState<RetryIntent | null>(null);

  // Filter once; downstream sections just receive arrays.
  const running = active.filter(
    (j) => j.status === 'running' || j.status === 'pending',
  );
  const paused = active.filter((j) => j.status === 'paused');
  const complete = history
    .filter((j) => j.status === 'complete')
    .slice(0, COMPLETE_VISIBLE_LIMIT);
  const failed = history.filter(
    (j) => j.status === 'failed' || j.status === 'cancelled',
  );

  // Look up the selected job from whichever group it's in. `useMemo`
  // avoids re-computing on every render when the hook returns fresh
  // array identities from polling.
  const selectedJob = useMemo<ExtractionJobWire | null>(() => {
    if (!selectedJobId) return null;
    return (
      active.find((j) => j.job_id === selectedJobId) ??
      history.find((j) => j.job_id === selectedJobId) ??
      null
    );
  }, [selectedJobId, active, history]);

  // Fetch the full Project lazily when the retry flow asks for it.
  // BuildGraphDialog requires a Project; the jobs tab only has a
  // project_id on the wire. `enabled` keeps this a no-op until the
  // user actually clicks Retry.
  const retryProjectQuery = useQuery({
    queryKey: ['knowledge-project', retryIntent?.projectId] as const,
    queryFn: () =>
      knowledgeApi.getProject(retryIntent!.projectId, accessToken!),
    enabled: !!retryIntent && !!accessToken,
    staleTime: 60_000,
  });

  // review-code L9: if the project fetch fails (e.g. user deleted the
  // project between panel open and retry click), surface the error as
  // a toast and reset the intent so the user isn't left wondering why
  // the dialog never appeared. useEffect is the correct hook here —
  // we're synchronising external UI (toast) with a reactive value
  // (query.error), not handling a user-action result.
  useEffect(() => {
    if (!retryIntent || !retryProjectQuery.error) return;
    const msg =
      retryProjectQuery.error instanceof Error
        ? retryProjectQuery.error.message
        : String(retryProjectQuery.error);
    toast.error(t('jobs.detail.actionFailed', { label: t('jobs.retry.button'), error: msg }));
    setRetryIntent(null);
  }, [retryIntent, retryProjectQuery.error, t]);

  const handleRetryClick = (job: ExtractionJobWire) => {
    // review-design R2: close the detail panel so BuildGraphDialog
    // doesn't appear over it.
    setSelectedJobId(null);
    setRetryIntent({
      projectId: job.project_id,
      initialValues: retryInitialsFromJob(job),
    });
  };

  const closeRetry = () => {
    setRetryIntent(null);
  };

  if (isLoading) {
    return (
      <div
        className="rounded-lg border bg-card px-6 py-10 text-center"
        data-testid="jobs-loading"
      >
        <p className="text-[13px] text-muted-foreground">{t('jobs.loading')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {activeError && (
        <ErrorBanner messageKey="jobs.error.active" error={activeError} />
      )}
      <Section
        title={t('jobs.sections.running.title')}
        emptyMessage={t('jobs.sections.running.empty')}
        jobs={running}
        onSelect={setSelectedJobId}
      />
      <Section
        title={t('jobs.sections.paused.title')}
        emptyMessage={t('jobs.sections.paused.empty')}
        jobs={paused}
        onSelect={setSelectedJobId}
        collapsedByDefault
      />
      {historyError && (
        <ErrorBanner messageKey="jobs.error.history" error={historyError} />
      )}
      <Section
        title={t('jobs.sections.complete.title')}
        emptyMessage={t('jobs.sections.complete.empty')}
        jobs={complete}
        onSelect={setSelectedJobId}
        collapsedByDefault
      />
      <Section
        title={t('jobs.sections.failed.title')}
        emptyMessage={t('jobs.sections.failed.empty')}
        jobs={failed}
        onSelect={setSelectedJobId}
        highlightWhenNonEmpty
      />

      <JobDetailPanel
        open={!!selectedJobId}
        onOpenChange={(o) => {
          if (!o) setSelectedJobId(null);
        }}
        job={selectedJob}
        onRetryClick={handleRetryClick}
      />

      {retryIntent && retryProjectQuery.data && (
        <BuildGraphDialog
          open={true}
          onOpenChange={(o) => {
            if (!o) closeRetry();
          }}
          project={retryProjectQuery.data}
          onStarted={closeRetry}
          initialValues={retryIntent.initialValues}
        />
      )}
    </div>
  );
}
