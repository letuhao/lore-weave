import { useTranslation } from 'react-i18next';

import { JobRow } from './JobRow';
import { useJobsList } from '../hooks/useJobsList';
import { jobKey, type Job } from '../types';

/** Children of a parent job, lazy-loaded via ?parent= when the row expands. */
export function JobChildrenTable({ parentJobId }: { parentJobId: string }) {
  const { t } = useTranslation('jobs');
  const q = useJobsList({ parent: parentJobId });
  const items: Job[] = q.data?.pages.flatMap((p) => p.items) ?? [];

  if (q.isLoading) {
    return (
      <p className="px-3 py-2 pl-10 text-[11px] text-muted-foreground">
        {t('list.loading', { defaultValue: 'Loading…' })}
      </p>
    );
  }
  if (items.length === 0) {
    return (
      <p className="px-3 py-2 pl-10 text-[11px] text-muted-foreground">
        {t('list.noChildren', { defaultValue: 'No child jobs.' })}
      </p>
    );
  }
  return (
    <div className="bg-secondary/20 pl-7">
      {items.map((j) => (
        <JobRow key={jobKey(j)} job={j} nested />
      ))}
      {q.hasNextPage && (
        <button
          className="px-3 py-2 pl-3 text-[11px] text-muted-foreground hover:text-foreground"
          onClick={() => q.fetchNextPage()}
          disabled={q.isFetchingNextPage}
        >
          {t('list.more', { defaultValue: 'Load more' })}
        </button>
      )}
    </div>
  );
}
