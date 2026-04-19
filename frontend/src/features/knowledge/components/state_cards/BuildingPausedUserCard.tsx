import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton } from './shared';
import type { ExtractionJobSummary } from '../../types/projectState';

interface Props {
  job: ExtractionJobSummary;
  onResume: () => void;
  onCancel: () => void;
}

export function BuildingPausedUserCard({ job, onResume, onCancel }: Props) {
  const { t } = useTranslation('knowledge');
  const spentLine = job.max_spend_usd
    ? t('projects.state.cards.building_running.spentOfBudget', {
        spent: job.cost_spent_usd,
        budget: job.max_spend_usd,
      })
    : t('projects.state.cards.building_running.spent', { spent: job.cost_spent_usd });
  return (
    <StateCardShell label={t('projects.state.labels.building_paused_user')}>
      <p className="text-muted-foreground">
        {t('projects.state.cards.building_paused_user.body')}
      </p>
      <p className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.building_running.progress', {
          processed: job.items_processed,
          total: job.items_total ?? '?',
        })}
      </p>
      <p className="text-[12px] text-muted-foreground">{spentLine}</p>
      <div className="flex gap-2 pt-1">
        <StateActionButton variant="primary" onClick={onResume}>
          {t('projects.state.actions.resume')}
        </StateActionButton>
        <StateActionButton variant="destructive" onClick={onCancel}>
          {t('projects.state.actions.cancel')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
