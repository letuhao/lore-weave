import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton, Spinner } from './shared';

// NOTE: the `estimating` state variant carries `scope: JobScope` but
// this card deliberately does NOT render it today. The estimating
// window is short (one API round-trip) and a bare "Chapters", "Chat"
// token would be low-value clutter. K19a.5 (BuildGraphDialog) owns the
// richer scope display surface; if the hook needs to convey scope to
// this card later, add a `scope` prop here then — don't plumb it
// through now for plumbing's sake.
interface Props {
  onCancel?: () => void;
}

export function EstimatingCard({ onCancel }: Props) {
  const { t } = useTranslation('knowledge');
  return (
    <StateCardShell label={t('projects.state.labels.estimating')}>
      <div className="flex items-center gap-2 text-muted-foreground">
        <Spinner />
        <span>{t('projects.state.cards.estimating.body')}</span>
      </div>
      {onCancel && (
        <div className="pt-1">
          <StateActionButton onClick={onCancel}>
            {t('projects.state.actions.cancel')}
          </StateActionButton>
        </div>
      )}
    </StateCardShell>
  );
}
