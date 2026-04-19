import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton } from './shared';

interface Props {
  onBuildGraph: () => void;
}

export function DisabledCard({ onBuildGraph }: Props) {
  const { t } = useTranslation('knowledge');
  return (
    <StateCardShell label={t('projects.state.labels.disabled')}>
      <p className="text-muted-foreground">{t('projects.state.cards.disabled.body')}</p>
      <p className="text-[12px] text-muted-foreground">{t('projects.state.cards.disabled.costZero')}</p>
      <div className="pt-1">
        <StateActionButton variant="primary" onClick={onBuildGraph}>
          {t('projects.state.actions.buildGraph')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
