import { useTranslation } from 'react-i18next';

import { JobSummaryCards } from './JobSummaryCards';
import { FairnessBanner } from './FairnessBanner';
import { JobsFilters } from './JobsFilters';
import { JobTableHeader } from './JobTableHeader';
import { JobRow } from './JobRow';
import { HistoryPager } from './HistoryPager';
import { useJobsDashboard } from '../hooks/useJobsDashboard';
import { useJobsConnection } from '../context/JobsStreamProvider';
import { jobKey, type Job } from '../types';

/** Desktop dashboard: live indicator + summary cards (quick-filters) + filter bar +
 *  Active table (live, unpaginated) + History table (offset+total, ORDER BY created).
 *
 *  `onOpenDetail` (studio dockable-migration injectable prop): forwarded to every JobRow
 *  unchanged. Omitted (the standalone /jobs page): behavior is byte-identical to before. */
export function JobsList({ onOpenDetail }: { onOpenDetail?: (service: string, jobId: string) => void } = {}) {
  const { t } = useTranslation('jobs');
  const d = useJobsDashboard();
  const conn = useJobsConnection();

  const activeItems: Job[] = d.active.data?.pages.flatMap((p) => p.items) ?? [];
  const historyItems: Job[] = d.history.data?.items ?? [];
  const total = d.history.data?.total ?? 0;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('title', { defaultValue: 'Jobs' })}</h1>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {conn === 'open' ? (
            <>
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-500" />
              {t('live.onShort', { defaultValue: 'live' })}
            </>
          ) : conn === 'reconnecting' || conn === 'connecting' ? (
            t('live.reconnecting', { defaultValue: 'reconnecting…' })
          ) : (
            t('live.off', { defaultValue: 'offline' })
          )}
        </span>
      </div>

      <JobSummaryCards summary={d.summary.data} selected={d.quick} onSelect={d.selectQuick} />

      <FairnessBanner />

      <JobsFilters kind={d.kind} onKind={d.changeKind} q={d.rawQ} onQ={d.changeQ} />

      {/* ── Active (live, unpaginated) ── */}
      {d.showActive && (
        <div className="overflow-hidden rounded-xl border bg-card">
          <div className="flex justify-between border-b bg-secondary px-4 py-2 text-[11px] uppercase tracking-wide text-muted-foreground">
            <span>{t('section.active', { defaultValue: 'Active · live' })}</span>
            <span className="normal-case tracking-normal">
              {t('section.activeHint', { defaultValue: 'not paginated — updates in place via SSE' })}
            </span>
          </div>
          <JobTableHeader />
          {d.active.isLoading ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">{t('list.loading', { defaultValue: 'Loading…' })}</p>
          ) : activeItems.length === 0 ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">{t('list.noActive', { defaultValue: 'No active jobs.' })}</p>
          ) : (
            activeItems.map((j) => <JobRow key={jobKey(j)} job={j} onOpenDetail={onOpenDetail} />)
          )}
          {d.active.hasNextPage && (
            <button
              type="button"
              className="w-full px-4 py-2 text-center text-xs text-muted-foreground hover:bg-accent/40 hover:text-foreground"
              onClick={() => d.active.fetchNextPage()}
              disabled={d.active.isFetchingNextPage}
            >
              {t('list.more', { defaultValue: 'Load more' })}
            </button>
          )}
        </div>
      )}

      {/* ── History (paginated) ── */}
      <div className="overflow-hidden rounded-xl border bg-card">
        <div className="flex justify-between border-b bg-secondary px-4 py-2 text-[11px] uppercase tracking-wide text-muted-foreground">
          <span>{t('section.history', { defaultValue: 'History' })}</span>
          <span className="normal-case tracking-normal">
            {t('section.historyHint', { defaultValue: 'sorted by created · paginated' })}
          </span>
        </div>
        <JobTableHeader />
        {d.history.isLoading ? (
          <p className="px-4 py-6 text-sm text-muted-foreground">{t('list.loading', { defaultValue: 'Loading…' })}</p>
        ) : d.history.error ? (
          <p className="px-4 py-6 text-sm text-destructive">{t('list.error', { defaultValue: 'Failed to load jobs.' })}</p>
        ) : historyItems.length === 0 ? (
          <p className="px-4 py-6 text-sm text-muted-foreground">{t('list.empty', { defaultValue: 'No jobs yet.' })}</p>
        ) : (
          historyItems.map((j) => <JobRow key={jobKey(j)} job={j} onOpenDetail={onOpenDetail} />)
        )}
      </div>
      <HistoryPager
        page={d.page}
        pageSize={d.pageSize}
        total={total}
        shown={historyItems.length}
        onPage={d.setPage}
        onPageSize={d.changePageSize}
      />
    </div>
  );
}
