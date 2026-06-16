import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { JobsFilters } from './JobsFilters';
import { JobRow } from './JobRow';
import { useJobsList } from '../hooks/useJobsList';
import { useJobsConnection } from '../context/JobsStreamProvider';
import { jobKey, type Job, type JobListParams } from '../types';

/** Desktop dashboard body: filter bar + live top-level rows (children grouped
 *  under their parent via JobRow's expander) + keyset "load more". */
export function JobsList() {
  const { t } = useTranslation('jobs');
  const [filters, setFilters] = useState<JobListParams>({});
  const q = useJobsList(filters);
  const conn = useJobsConnection();
  const items: Job[] = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{t('title', { defaultValue: 'Jobs' })}</h1>
        <span className="text-[11px] text-muted-foreground">
          {conn === 'open'
            ? t('live.on', { defaultValue: '● live' })
            : conn === 'reconnecting'
              ? t('live.reconnecting', { defaultValue: 'reconnecting…' })
              : t('live.off', { defaultValue: 'offline' })}
        </span>
      </div>

      <JobsFilters filters={filters} onChange={setFilters} />

      {q.isLoading ? (
        <p className="text-sm text-muted-foreground">{t('list.loading', { defaultValue: 'Loading…' })}</p>
      ) : q.error ? (
        <p className="text-sm text-destructive">{t('list.error', { defaultValue: 'Failed to load jobs.' })}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('list.empty', { defaultValue: 'No jobs yet.' })}</p>
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((j) => (
            <JobRow key={jobKey(j)} job={j} />
          ))}
          {q.hasNextPage && (
            <button
              className="self-center rounded-lg border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
              onClick={() => q.fetchNextPage()}
              disabled={q.isFetchingNextPage}
            >
              {t('list.more', { defaultValue: 'Load more' })}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
