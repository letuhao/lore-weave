// C24 (dị bản M0) — the 4-step divergence wizard (view shell). Hosts the step
// bodies and the nav/submit footer. Logic + state live in useDivergenceWizard.
//
// FE-rule compliance:
//  • ALL 4 step bodies stay MOUNTED — only the active one is visible (CSS hidden).
//    No `{step===1 ? <A/> : <B/>}` ternary that would unmount + destroy a step's
//    in-flight draft state (adversary: conditional-unmount).
//  • Next/Back/Submit are explicit onClick handlers calling the controller's
//    callbacks — no useEffect-for-events.
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared/FormDialog';
import { useDivergenceWizard } from '../hooks/useDivergenceWizard';
import type { Work } from '../types';
import { Step1Source, Step2Type, Step3Overrides, Step4Name } from './DivergenceWizardSteps';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sourceWork: Work;
  token: string | null;
  onDerived?: (derivative: Work) => void;
};

export function DivergenceWizard({ open, onOpenChange, sourceWork, token, onDerived }: Props) {
  const { t } = useTranslation('composition');
  const w = useDivergenceWizard({
    sourceWork,
    token,
    onDerived: (d) => {
      onDerived?.(d);
      onOpenChange(false);
    },
  });

  const stepLabels = [
    t('derive.stepSource', { defaultValue: 'Source' }),
    t('derive.stepType', { defaultValue: 'Type' }),
    t('derive.stepOverrides', { defaultValue: 'Overrides' }),
    t('derive.stepName', { defaultValue: 'Name' }),
  ];

  const footer = (
    <div className="flex w-full items-center justify-between">
      <button
        type="button"
        data-testid="divergence-back"
        className="rounded px-3 py-1.5 text-sm text-neutral-600 disabled:opacity-40 dark:text-neutral-300"
        onClick={w.goBack}
        disabled={w.step === 1 || w.isSubmitting}
      >
        {t('derive.back', { defaultValue: 'Back' })}
      </button>
      {w.error && <span data-testid="divergence-error" className="text-xs text-red-600">{w.error}</span>}
      {w.step < 4 ? (
        <button
          type="button"
          data-testid="divergence-next"
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          onClick={w.goNext}
          disabled={!w.canAdvance}
        >
          {t('derive.next', { defaultValue: 'Next' })}
        </button>
      ) : (
        <button
          type="button"
          data-testid="divergence-submit"
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          onClick={w.submit}
          disabled={!w.canAdvance || w.isSubmitting}
        >
          {w.isSubmitting ? t('derive.spawning', { defaultValue: 'Spawning…' }) : t('derive.spawn', { defaultValue: 'Spawn what-if' })}
        </button>
      )}
    </div>
  );

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('derive.title', { defaultValue: 'Spawn a what-if (derivative)' })}
      footer={footer}
    >
      <div className="flex flex-col gap-3" data-testid="divergence-wizard">
        {/* step rail */}
        <ol className="flex items-center gap-1 text-xs" data-testid="divergence-rail">
          {stepLabels.map((label, i) => {
            const n = (i + 1) as 1 | 2 | 3 | 4;
            const active = w.step === n;
            return (
              <li key={label} className="flex items-center gap-1">
                <span
                  className={
                    'flex h-5 w-5 items-center justify-center rounded-full text-[10px] ' +
                    (active ? 'bg-indigo-600 text-white' : 'bg-neutral-200 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300')
                  }
                >
                  {n}
                </span>
                <span className={active ? 'font-medium' : 'text-neutral-400'}>{label}</span>
                {i < stepLabels.length - 1 && <span className="text-neutral-300">→</span>}
              </li>
            );
          })}
        </ol>

        {/* All 4 steps stay MOUNTED; only the active one is shown (no unmount). */}
        <div className={w.step === 1 ? '' : 'hidden'}>
          <Step1Source bookId={sourceWork.book_id} branchPoint={w.branchPoint} setBranchPoint={w.setBranchPoint} token={token} />
        </div>
        <div className={w.step === 2 ? '' : 'hidden'}>
          <Step2Type taxonomy={w.taxonomy} setTaxonomy={w.setTaxonomy} />
        </div>
        <div className={w.step === 3 ? '' : 'hidden'}>
          <Step3Overrides
            sourceProjectId={sourceWork.project_id}
            overrides={w.overrides}
            setOverride={w.setOverride}
            canonRules={w.canonRules}
            setCanonRules={w.setCanonRules}
            token={token}
          />
        </div>
        <div className={w.step === 4 ? '' : 'hidden'}>
          <Step4Name name={w.name} setName={w.setName} />
        </div>
      </div>
    </FormDialog>
  );
}
