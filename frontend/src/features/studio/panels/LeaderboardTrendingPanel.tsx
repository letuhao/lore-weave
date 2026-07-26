// 14_utility_panels.md D2 — the "trending" leaderboard capability (same book-ranking shape as
// "books" — Podium + RankingList — but WITHOUT QuickStatsCards, matching LeaderboardPage's
// original trending tab), driven by useLeaderboardList('trending') (D1). The hook forces the
// `sort` param to 'trending' server-side for this kind regardless of the local sort filter (same
// behavior as the original page's `activeTab === 'trending'` override). Owns its OWN
// period/genre/language filter state independently of the other 3 leaderboard panels (no
// cross-panel sync this cycle — D2's accepted simplification).
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { PeriodSelector } from '@/features/leaderboard/PeriodSelector';
import { FilterChips } from '@/features/leaderboard/FilterChips';
import { Podium } from '@/features/leaderboard/Podium';
import { RankingList } from '@/features/leaderboard/RankingList';
import { useLeaderboardList } from '@/features/leaderboard/hooks/useLeaderboardList';
import { useStudioPanel } from './useStudioPanel';

export function LeaderboardTrendingPanel(props: IDockviewPanelProps) {
  useStudioPanel('leaderboard-trending', props.api);
  const { t } = useTranslation('leaderboard');
  const lb = useLeaderboardList('trending');

  return (
    <div data-testid="studio-leaderboard-trending-panel" className="h-full min-h-0 space-y-4 overflow-auto p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FilterChips
          genre={lb.genre}
          language={lb.language}
          onGenreChange={lb.setGenre}
          onLanguageChange={lb.setLanguage}
        />
        <PeriodSelector value={lb.period} onChange={lb.setPeriod} />
      </div>

      {lb.isLoading && lb.books.length === 0 && (
        <div className="space-y-4">
          <Skeleton className="h-48 w-full rounded-lg" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      )}

      {!lb.isLoading && lb.books.length === 0 && (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          {t('ranking.noResults')}
        </div>
      )}

      {lb.books.length > 0 && (
        <div className="space-y-4">
          {lb.showPodium && <Podium books={lb.books.slice(0, 3)} />}

          <RankingList
            books={lb.books}
            sort={lb.sort}
            onSortChange={lb.setSort}
            hasMore={lb.books.length < lb.booksTotal}
            onLoadMore={() => lb.fetchBooks(lb.books.length, true)}
            loading={lb.booksLoading}
          />
        </div>
      )}
    </div>
  );
}
