// 14_utility_panels.md D2 — the "authors" leaderboard capability, driven by
// useLeaderboardList('authors') (D1). Owns its OWN period filter state independently of the
// other 3 leaderboard panels (no cross-panel sync this cycle — D2's accepted simplification).
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { PeriodSelector } from '@/features/leaderboard/PeriodSelector';
import { AuthorList } from '@/features/leaderboard/AuthorList';
import { useLeaderboardList } from '@/features/leaderboard/hooks/useLeaderboardList';
import { useStudioPanel } from './useStudioPanel';

export function LeaderboardAuthorsPanel(props: IDockviewPanelProps) {
  useStudioPanel('leaderboard-authors', props.api);
  const { t } = useTranslation('leaderboard');
  const lb = useLeaderboardList('authors');

  return (
    <div data-testid="studio-leaderboard-authors-panel" className="h-full min-h-0 space-y-4 overflow-auto p-4">
      <div className="flex justify-end">
        <PeriodSelector value={lb.period} onChange={lb.setPeriod} />
      </div>

      {lb.isLoading && lb.authors.length === 0 && (
        <div className="space-y-4">
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      )}

      {lb.authors.length > 0 && (
        <AuthorList
          authors={lb.authors}
          hasMore={lb.authors.length < lb.authorsTotal}
          onLoadMore={() => lb.fetchAuthors(lb.authors.length, true)}
          loading={lb.authorsLoading}
        />
      )}

      {!lb.isLoading && lb.authors.length === 0 && (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          {t('ranking.noResults')}
        </div>
      )}
    </div>
  );
}
