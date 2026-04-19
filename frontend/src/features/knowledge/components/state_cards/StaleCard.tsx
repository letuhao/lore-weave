import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton } from './shared';
import type { GraphStats } from '../../types/projectState';

interface Props {
  stats: GraphStats;
  pendingCount: number;
  onExtractNew: () => void;
  onIgnoreStale: () => void;
}

export function StaleCard({ stats, pendingCount, onExtractNew, onIgnoreStale }: Props) {
  const { t } = useTranslation('knowledge');
  return (
    <StateCardShell label={t('projects.state.labels.stale')}>
      <p className="text-muted-foreground">
        {t('projects.state.cards.stale.body', { count: pendingCount })}
      </p>
      <p className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.complete.stats', {
          entities: stats.entity_count,
          facts: stats.fact_count,
          events: stats.event_count,
          passages: stats.passage_count,
        })}
      </p>
      <div className="flex gap-2 pt-1">
        <StateActionButton variant="primary" onClick={onExtractNew}>
          {t('projects.state.actions.extractNew')}
        </StateActionButton>
        <StateActionButton onClick={onIgnoreStale}>
          {t('projects.state.actions.ignore')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
