import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton, ProgressBar } from './shared';
import type { ExtractionJobSummary } from '../../types/projectState';

interface Props {
  job: ExtractionJobSummary;
  error: string;
  onRetry: () => void;
  onCancel: () => void;
  onViewError: () => void;
}

export function BuildingPausedErrorCard({ job, error, onRetry, onCancel, onViewError }: Props) {
  const { t } = useTranslation('knowledge');
  const spentLine = job.max_spend_usd
    ? t('projects.state.cards.building_running.spentOfBudget', {
        spent: job.cost_spent_usd,
        budget: job.max_spend_usd,
      })
    : t('projects.state.cards.building_running.spent', { spent: job.cost_spent_usd });
  return (
    <StateCardShell label={t('projects.state.labels.building_paused_error')}>
      <p className="text-muted-foreground">
        {t('projects.state.cards.building_paused_error.body', { error })}
      </p>
      <ProgressBar processed={job.items_processed} total={job.items_total} />
      <p className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.building_running.progress', {
          processed: job.items_processed,
          total: job.items_total ?? '?',
        })}
      </p>
      <p className="text-[12px] text-muted-foreground">{spentLine}</p>
      <div className="flex gap-2 pt-1">
        <StateActionButton variant="primary" onClick={onRetry}>
          {t('projects.state.actions.retry')}
        </StateActionButton>
        <StateActionButton onClick={onViewError}>
          {t('projects.state.actions.viewError')}
        </StateActionButton>
        <StateActionButton variant="destructive" onClick={onCancel}>
          {t('projects.state.actions.cancel')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
