import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton } from './shared';

interface Props {
  oldModel: string;
  newModel: string;
  onConfirmModelChange: () => void;
  onCancel: () => void;
}

export function ModelChangePendingCard({
  oldModel,
  newModel,
  onConfirmModelChange,
  onCancel,
}: Props) {
  const { t } = useTranslation('knowledge');
  return (
    <StateCardShell
      label={t('projects.state.labels.model_change_pending')}
      className="border-warning/30"
    >
      <p className="text-muted-foreground">
        {t('projects.state.cards.model_change_pending.body', { oldModel, newModel })}
      </p>
      <div className="flex gap-2 pt-1">
        <StateActionButton variant="destructive" onClick={onConfirmModelChange}>
          {t('projects.state.actions.confirm')}
        </StateActionButton>
        <StateActionButton onClick={onCancel}>
          {t('projects.state.actions.cancel')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
