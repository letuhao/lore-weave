import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useJobLogs } from '../hooks/useJobLogs';
import type { JobLog, JobLogLevel } from '../api';

// K19b.8 — collapsible log panel rendered inside JobDetailPanel.
// Consumes the single-page `useJobLogs` hook; renders a compact
// timestamped list. Collapsed by default so the panel's key
// surfaces (progress, actions, error) render above the fold.

const LEVEL_CLASS: Record<JobLogLevel, string> = {
  info: 'bg-muted text-muted-foreground',
  warning: 'bg-amber-500/20 text-amber-700 dark:text-amber-300',
  error: 'bg-destructive/15 text-destructive',
};

const SHORT_DATE_FORMATTER = new Intl.DateTimeFormat(undefined, {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

function formatShortTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return SHORT_DATE_FORMATTER.format(d);
}

function LogRow({ log }: { log: JobLog }) {
  const { t } = useTranslation('knowledge');
  return (
    <li
      className="flex items-baseline gap-2 border-b border-border/50 py-1 last:border-b-0"
      data-testid="job-log-row"
      data-log-id={log.log_id}
      data-level={log.level}
    >
      <span
        className={cn(
          'inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
          LEVEL_CLASS[log.level],
        )}
      >
        {t(`jobs.detail.logs.levels.${log.level}`)}
      </span>
      <time
        className="shrink-0 text-[11px] tabular-nums text-muted-foreground"
        dateTime={log.created_at}
      >
        {formatShortTime(log.created_at)}
      </time>
      <span className="min-w-0 break-words text-[12px]">{log.message}</span>
    </li>
  );
}

export function JobLogsPanel({ jobId }: { jobId: string }) {
  const { t } = useTranslation('knowledge');
  const { logs, nextCursor, isLoading, error } = useJobLogs(jobId);
  // review-code L6: `nextCursor != null` is the semantic "more may
  // exist" signal from the BE, not a magic-number comparison against
  // DEFAULT_LIMIT. Survives any future limit change in the hook.
  const hasMore = nextCursor != null;

  return (
    <details
      className="rounded-md border bg-muted/30"
      data-testid="job-logs-panel"
    >
      <summary className="cursor-pointer select-none px-3 py-2 text-[12px] font-medium">
        {t('jobs.detail.logs.title')}
        <span className="ml-2 text-[11px] font-normal text-muted-foreground">
          ({logs.length}
          {hasMore ? '+' : ''})
        </span>
      </summary>
      <div className="border-t px-3 py-2">
        {isLoading && (
          <p
            className="text-[12px] text-muted-foreground"
            data-testid="job-logs-loading"
          >
            {t('jobs.detail.logs.loading')}
          </p>
        )}
        {error && !isLoading && (
          <p
            className="text-[12px] text-destructive"
            data-testid="job-logs-error"
          >
            {t('jobs.detail.logs.error')}
            <span className="ml-2 text-destructive/80">{error.message}</span>
          </p>
        )}
        {!isLoading && !error && logs.length === 0 && (
          <p
            className="text-[12px] text-muted-foreground"
            data-testid="job-logs-empty"
          >
            {t('jobs.detail.logs.empty')}
          </p>
        )}
        {!isLoading && !error && logs.length > 0 && (
          <ul className="space-y-0">
            {logs.map((log) => (
              <LogRow key={log.log_id} log={log} />
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
