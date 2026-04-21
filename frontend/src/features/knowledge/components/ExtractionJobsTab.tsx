import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useExtractionJobs } from '../hooks/useExtractionJobs';
import type { ExtractionJobWire } from '../api';
import { JobProgressBar } from './JobProgressBar';

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
          jobs.map((j) => <JobRow key={j.job_id} job={j} />)
        )}
      </div>
    </details>
  );
}

function JobRow({ job }: { job: ExtractionJobWire }) {
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

  return (
    <div
      className="grid grid-cols-[minmax(0,1fr)_200px] items-center gap-3 text-[13px]"
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

export function ExtractionJobsTab() {
  const { t } = useTranslation('knowledge');
  const { active, history, isLoading, activeError, historyError } =
    useExtractionJobs();

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
      />
      <Section
        title={t('jobs.sections.paused.title')}
        emptyMessage={t('jobs.sections.paused.empty')}
        jobs={paused}
        collapsedByDefault
      />
      {historyError && (
        <ErrorBanner messageKey="jobs.error.history" error={historyError} />
      )}
      <Section
        title={t('jobs.sections.complete.title')}
        emptyMessage={t('jobs.sections.complete.empty')}
        jobs={complete}
        collapsedByDefault
      />
      <Section
        title={t('jobs.sections.failed.title')}
        emptyMessage={t('jobs.sections.failed.empty')}
        jobs={failed}
        highlightWhenNonEmpty
      />
    </div>
  );
}
