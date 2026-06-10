import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import { WIZARD_STEPS } from '../hooks/useCampaignWizard';

interface Props {
  current: number;
}

/** S5c — the wizard's step indicator (view-only). Renders the 4 steps with a
 *  done/active/upcoming state derived from `current`. */
export function WizardStepper({ current }: Props) {
  const { t } = useTranslation('campaigns');
  const labels: Record<string, string> = {
    bookProject: t('steps.bookProject', { defaultValue: 'Book & Project' }),
    range: t('steps.range', { defaultValue: 'Chapters' }),
    models: t('steps.models', { defaultValue: 'Models' }),
    review: t('steps.review', { defaultValue: 'Review & Launch' }),
  };
  return (
    <ol className="flex items-center gap-2" aria-label={t('steps.aria', { defaultValue: 'Setup steps' })}>
      {WIZARD_STEPS.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={s} className="flex items-center gap-2">
            <span
              className={[
                'flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium',
                done ? 'bg-primary text-primary-foreground'
                  : active ? 'border-2 border-primary text-primary'
                    : 'border border-muted-foreground/40 text-muted-foreground',
              ].join(' ')}
              aria-current={active ? 'step' : undefined}
            >
              {done ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </span>
            <span className={active ? 'text-sm font-medium' : 'text-sm text-muted-foreground'}>
              {labels[s]}
            </span>
            {i < WIZARD_STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-border" />}
          </li>
        );
      })}
    </ol>
  );
}
