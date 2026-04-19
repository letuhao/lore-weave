import { useTranslation } from 'react-i18next';
import { StateCardShell, Spinner } from './shared';

export function DeletingCard() {
  const { t } = useTranslation('knowledge');
  return (
    <StateCardShell label={t('projects.state.labels.deleting')}>
      <div className="flex items-center gap-2 text-muted-foreground">
        <Spinner />
        <span>{t('projects.state.cards.deleting.body')}</span>
      </div>
    </StateCardShell>
  );
}
