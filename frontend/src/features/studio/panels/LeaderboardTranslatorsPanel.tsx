// 14_utility_panels.md D2 — the "translators" leaderboard capability, driven by
// useLeaderboardList('translators') (D1). Owns its OWN period filter state independently of the
// other 3 leaderboard panels (no cross-panel sync this cycle — D2's accepted simplification).
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { PeriodSelector } from '@/features/leaderboard/PeriodSelector';
import { TranslatorList } from '@/features/leaderboard/TranslatorList';
import { useLeaderboardList } from '@/features/leaderboard/hooks/useLeaderboardList';
import { useStudioPanel } from './useStudioPanel';

export function LeaderboardTranslatorsPanel(props: IDockviewPanelProps) {
  useStudioPanel('leaderboard-translators', props.api);
  const { t } = useTranslation('leaderboard');
  const lb = useLeaderboardList('translators');

  return (
    <div data-testid="studio-leaderboard-translators-panel" className="h-full min-h-0 space-y-4 overflow-auto p-4">
      <div className="flex justify-end">
        <PeriodSelector value={lb.period} onChange={lb.setPeriod} />
      </div>

      {lb.isLoading && lb.translators.length === 0 && (
        <div className="space-y-4">
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      )}

      {lb.translators.length > 0 && (
        <TranslatorList
          translators={lb.translators}
          hasMore={lb.translators.length < lb.translatorsTotal}
          onLoadMore={() => lb.fetchTranslators(lb.translators.length, true)}
          loading={lb.translatorsLoading}
        />
      )}

      {!lb.isLoading && lb.translators.length === 0 && (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          {t('ranking.noResults')}
        </div>
      )}
    </div>
  );
}
