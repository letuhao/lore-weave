// 14_utility_panels.md D2 — the "books" leaderboard capability (Podium + QuickStatsCards +
// RankingList, since these live together on LeaderboardPage's "books" tab today), driven by
// useLeaderboardList('books') (D1). DOCK-8 fix: the page's internal 4-tab view-switch becomes
// 4 separate catalog entries instead of a branch inside one panel. This panel owns its OWN
// period/genre/language/sort filter state (no cross-panel filter sync this cycle — D2's
// accepted simplification). "View all" in QuickStatsCards opens the sibling authors/translators
// dock panel via host.openPanel (DOCK-7 compliant — not a route hop).
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { PeriodSelector } from '@/features/leaderboard/PeriodSelector';
import { FilterChips } from '@/features/leaderboard/FilterChips';
import { Podium } from '@/features/leaderboard/Podium';
import { RankingList } from '@/features/leaderboard/RankingList';
import { QuickStatsCards } from '@/features/leaderboard/QuickStatsCards';
import { useLeaderboardList } from '@/features/leaderboard/hooks/useLeaderboardList';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function LeaderboardBooksPanel(props: IDockviewPanelProps) {
  useStudioPanel('leaderboard-books', props.api);
  const { t } = useTranslation('leaderboard');
  const host = useStudioHost();
  const lb = useLeaderboardList('books');

  return (
    <div data-testid="studio-leaderboard-books-panel" className="h-full min-h-0 space-y-4 overflow-auto p-4">
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

          <QuickStatsCards
            authors={lb.previewAuthors}
            translators={lb.previewTranslators}
            onViewAuthors={() => host.openPanel('leaderboard-authors')}
            onViewTranslators={() => host.openPanel('leaderboard-translators')}
          />
        </div>
      )}
    </div>
  );
}
