import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton } from './shared';
import type { ExtractionJobSummary } from '../../types/projectState';

interface Props {
  job: ExtractionJobSummary;
  budgetRemaining: number;
  onResume: () => void;
  onCancel: () => void;
}

export function BuildingPausedBudgetCard({
  job,
  budgetRemaining,
  onResume,
  onCancel,
}: Props) {
  const { t } = useTranslation('knowledge');
  return (
    <StateCardShell label={t('projects.state.labels.building_paused_budget')}>
      <p className="text-muted-foreground">
        {t('projects.state.cards.building_paused_budget.body', {
          budget: job.max_spend_usd ?? '?',
        })}
      </p>
      <p className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.building_running.spentOfBudget', {
          spent: job.cost_spent_usd,
          budget: job.max_spend_usd ?? '?',
        })}
      </p>
      <p className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.building_paused_budget.remaining', {
          amount: budgetRemaining.toFixed(2),
        })}
      </p>
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
