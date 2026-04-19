import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton } from './shared';

interface Props {
  error: string;
  canRetry: boolean;
  onRetry: () => void;
  onDeleteGraph: () => void;
  onViewError: () => void;
}

export function FailedCard({ error, canRetry, onRetry, onDeleteGraph, onViewError }: Props) {
  const { t } = useTranslation('knowledge');
  return (
    <StateCardShell
      label={t('projects.state.labels.failed')}
      className="border-destructive/30"
    >
      <p className="text-destructive">
        {t('projects.state.cards.failed.body', { error })}
      </p>
      <div className="flex gap-2 pt-1">
        {canRetry && (
          <StateActionButton variant="primary" onClick={onRetry}>
            {t('projects.state.actions.retry')}
          </StateActionButton>
        )}
        <StateActionButton onClick={onViewError}>
          {t('projects.state.actions.viewError')}
        </StateActionButton>
        <StateActionButton variant="destructive" onClick={onDeleteGraph}>
          {t('projects.state.actions.deleteGraph')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
