import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton } from './shared';
import type { GraphStats } from '../../types/projectState';

interface Props {
  stats: GraphStats;
  onExtractNew: () => void;
  onRebuild: () => void;
  onChangeModel: () => void;
  onDeleteGraph: () => void;
  onDisable: () => void;
}

export function CompleteCard({
  stats,
  onExtractNew,
  onRebuild,
  onChangeModel,
  onDeleteGraph,
  onDisable,
}: Props) {
  const { t } = useTranslation('knowledge');
  return (
    <StateCardShell label={t('projects.state.labels.complete')}>
      <p className="text-muted-foreground">
        {t('projects.state.cards.complete.stats', {
          entities: stats.entity_count,
          facts: stats.fact_count,
          events: stats.event_count,
          passages: stats.passage_count,
        })}
      </p>
      <p className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.complete.lastExtracted', {
          date: stats.last_extracted_at.slice(0, 10),
        })}
      </p>
      <div className="flex flex-wrap gap-2 pt-1">
        <StateActionButton variant="primary" onClick={onExtractNew}>
          {t('projects.state.actions.extractNew')}
        </StateActionButton>
        <StateActionButton onClick={onRebuild}>
          {t('projects.state.actions.rebuild')}
        </StateActionButton>
        <StateActionButton onClick={onChangeModel}>
          {t('projects.state.actions.changeModel')}
        </StateActionButton>
        <StateActionButton variant="destructive" onClick={onDeleteGraph}>
          {t('projects.state.actions.deleteGraph')}
        </StateActionButton>
        <StateActionButton onClick={onDisable}>
          {t('projects.state.actions.disable')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
