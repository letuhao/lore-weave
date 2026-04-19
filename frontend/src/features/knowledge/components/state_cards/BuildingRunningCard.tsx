import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton, ProgressBar } from './shared';
import type { ExtractionJobSummary } from '../../types/projectState';

interface Props {
  job: ExtractionJobSummary;
  onPause: () => void;
  onCancel: () => void;
}

export function BuildingRunningCard({ job, onPause, onCancel }: Props) {
  const { t } = useTranslation('knowledge');
  const spentLine = job.max_spend_usd
    ? t('projects.state.cards.building_running.spentOfBudget', {
        spent: job.cost_spent_usd,
        budget: job.max_spend_usd,
      })
    : t('projects.state.cards.building_running.spent', { spent: job.cost_spent_usd });

  return (
    <StateCardShell label={t('projects.state.labels.building_running')}>
      <ProgressBar processed={job.items_processed} total={job.items_total} />
      <p className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.building_running.progress', {
          processed: job.items_processed,
          total: job.items_total ?? '?',
        })}
      </p>
      <p className="text-[12px] text-muted-foreground">{spentLine}</p>
      <div className="flex gap-2 pt-1">
        <StateActionButton onClick={onPause}>
          {t('projects.state.actions.pause')}
        </StateActionButton>
        <StateActionButton variant="destructive" onClick={onCancel}>
          {t('projects.state.actions.cancel')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
