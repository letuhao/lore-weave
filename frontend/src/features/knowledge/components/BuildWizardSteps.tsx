import { useTranslation } from 'react-i18next';

// C12 — 3-step build-wizard SHELL. A controlled step indicator + body slot.
// Deliberately dumb (no own state) so C13 can drop the Step-2 pinning dual-list
// into the same shell without touching this. The parent owns the active step.
export type WizardStep = 1 | 2 | 3;

interface Props {
  step: WizardStep;
  onStepChange: (step: WizardStep) => void;
  children: React.ReactNode;
}

const STEPS: { id: WizardStep; key: string }[] = [
  { id: 1, key: 'step1' },
  { id: 2, key: 'step2' },
  { id: 3, key: 'step3' },
];

export function BuildWizardSteps({ step, onStepChange, children }: Props) {
  const { t } = useTranslation('knowledge');

  return (
    <div className="flex flex-col gap-3" data-testid="build-wizard">
      {/* Step indicator — clickable to jump between steps (all are optional;
          targets default to all, pinning is empty, budget is optional). */}
      <ol className="flex items-center gap-2 text-xs" data-testid="build-wizard-steps">
        {STEPS.map((s, i) => {
          const active = s.id === step;
          return (
            <li key={s.id} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onStepChange(s.id)}
                aria-current={active ? 'step' : undefined}
                data-testid={`build-wizard-step-${s.id}`}
                className={[
                  'flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium',
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-secondary',
                ].join(' ')}
              >
                <span
                  className={[
                    'flex h-4 w-4 items-center justify-center rounded-full text-[10px]',
                    active ? 'bg-primary-foreground text-primary' : 'bg-secondary',
                  ].join(' ')}
                >
                  {s.id}
                </span>
                {t(`projects.buildDialog.wizard.${s.key}`)}
              </button>
              {i < STEPS.length - 1 && (
                <span className="text-muted-foreground">›</span>
              )}
            </li>
          );
        })}
      </ol>
      <div>{children}</div>
    </div>
  );
}
