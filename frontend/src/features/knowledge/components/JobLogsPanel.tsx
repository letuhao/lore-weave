import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useJobLogs } from '../hooks/useJobLogs';
import type { JobLog, JobLogLevel } from '../api';

// K19b.8 — collapsible log panel rendered inside JobDetailPanel.
// C3 (D-K19b.8-03) — tail-follow (auto-refetch while job is running,
// triggered inside useJobLogs based on `jobStatus` prop) + cursor
// pagination via "Load newer" + near-bottom auto-scroll (only scrolls
// when user is within 100px of the bottom so reading earlier logs
// isn't disrupted).
//
// /review-impl L8 — the log list is not virtualised. For a long-
// running job that accumulates 10k+ rows across many "Load newer"
// clicks, the DOM gets sluggish. Hobby-scale deploys stay well
// under that. Real scale-up would swap the `<ul>` for react-window
// or react-virtual — out of C3 scope.

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

// C3: auto-scroll fires only when user is within this many pixels of
// the bottom. A user scrolled up to read earlier logs shouldn't be
// yanked back down on every poll.
const NEAR_BOTTOM_THRESHOLD_PX = 100;

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

export interface JobLogsPanelProps {
  jobId: string;
  /**
   * C3: passed to useJobLogs so the hook can enable the 5s
   * refetch interval only while the job is still active.
   */
  jobStatus?: string | null;
}

export function JobLogsPanel({ jobId, jobStatus }: JobLogsPanelProps) {
  const { t } = useTranslation('knowledge');
  const {
    logs,
    hasNextPage,
    fetchNextPage,
    isLoading,
    isFetchingNextPage,
    error,
  } = useJobLogs(jobId, { jobStatus });

  // C3 auto-scroll. `nearBottomRef` tracks whether the user was near
  // the bottom on their most recent scroll event. When new logs
  // arrive, scroll to bottom only if that flag is true. Initial
  // render assumes near-bottom (desirable — show latest on open).
  const listRef = useRef<HTMLUListElement | null>(null);
  const nearBottomRef = useRef(true);

  const recomputeNearBottom = () => {
    const el = listRef.current;
    if (!el) return;
    nearBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_THRESHOLD_PX;
  };

  const handleScroll = () => recomputeNearBottom();

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    if (!nearBottomRef.current) return;
    // New logs arrived and user was near bottom — follow the tail.
    el.scrollTo({ top: el.scrollHeight });
  }, [logs.length]);

  // /review-impl L6 — re-sync nearBottomRef on container resize so
  // a browser-resize mid-session doesn't leave the flag reflecting
  // pre-resize geometry. Guarded for SSR + legacy envs where
  // ResizeObserver is missing.
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      recomputeNearBottom();
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // /review-impl M1 — `<details>` re-open auto-scroll. Without this,
  // a user collapsing the panel while logs accumulate in the
  // background then re-opening would land at scrollTop=0 (oldest
  // row at top) regardless of `nearBottomRef`. Force a scroll-to-
  // bottom on open so "show latest" is the default UX.
  // Wrapped in rAF so the `<ul>` has time to become visible and
  // report its real scrollHeight (collapsed = 0 in every browser).
  const handleToggle = (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    if (!e.currentTarget.open) return;
    requestAnimationFrame(() => {
      const el = listRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight });
      nearBottomRef.current = true;
    });
  };

  return (
    <details
      className="rounded-md border bg-muted/30"
      data-testid="job-logs-panel"
      onToggle={handleToggle}
    >
      <summary className="cursor-pointer select-none px-3 py-2 text-[12px] font-medium">
        {t('jobs.detail.logs.title')}
        <span className="ml-2 text-[11px] font-normal text-muted-foreground">
          ({logs.length}
          {hasNextPage ? '+' : ''})
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
          <>
            <ul
              ref={listRef}
              onScroll={handleScroll}
              className="max-h-80 space-y-0 overflow-y-auto"
              data-testid="job-logs-list"
            >
              {logs.map((log) => (
                <LogRow key={log.log_id} log={log} />
              ))}
            </ul>
            {hasNextPage && (
              <button
                type="button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className={cn(
                  'mt-2 w-full rounded border border-border/50 bg-background px-2 py-1 text-[11px] font-medium text-muted-foreground',
                  'hover:bg-muted/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary',
                  'disabled:cursor-not-allowed disabled:opacity-60',
                )}
                data-testid="job-logs-load-more"
              >
                {isFetchingNextPage
                  ? t('jobs.detail.logs.loadingNewer')
                  : t('jobs.detail.logs.loadNewer')}
              </button>
            )}
          </>
        )}
      </div>
    </details>
  );
}
