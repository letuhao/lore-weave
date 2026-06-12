import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useCampaignWizard } from '../hooks/useCampaignWizard';
import { WizardStepper } from './WizardStepper';
import { BookProjectStep } from './steps/BookProjectStep';
import { ChapterRangeStep } from './steps/ChapterRangeStep';
import { ModelMatrixStep } from './steps/ModelMatrixStep';
import { ReviewStep } from './steps/ReviewStep';

/** /campaigns/new (view + controller wiring): renders the stepper, the active
 *  step, and Back/Next. The wizard hook owns all state + payload assembly. */
export function CampaignWizard() {
  const { t } = useTranslation('campaigns');
  const navigate = useNavigate();
  const wiz = useCampaignWizard();

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t('wizard.title', { defaultValue: 'New Auto-Draft Campaign' })}</h1>
        <Link to="/campaigns" className="text-sm text-muted-foreground hover:text-foreground">
          {t('wizard.cancel', { defaultValue: 'Cancel' })}
        </Link>
      </div>

      <WizardStepper current={wiz.stepIndex} />

      <div className="min-h-[16rem]">
        {wiz.step === 'bookProject' && <BookProjectStep form={wiz.form} setField={wiz.setField} />}
        {wiz.step === 'range' && <ChapterRangeStep form={wiz.form} setField={wiz.setField} />}
        {wiz.step === 'models' && <ModelMatrixStep form={wiz.form} setPick={wiz.setPick} setField={wiz.setField} />}
        {wiz.step === 'review' && (
          <ReviewStep
            buildEstimateRequest={wiz.buildEstimateRequest}
            buildCreatePayload={wiz.buildCreatePayload}
            budgetUsd={wiz.form.budgetUsd}
            setBudget={(v) => wiz.setField('budgetUsd', v)}
            onLaunched={(id) => navigate(`/campaigns/${id}`)}
            onEstimated={(lo, hi) => { wiz.setField('estUsdLow', lo); wiz.setField('estUsdHigh', hi); }}
          />
        )}
      </div>

      <div className="flex items-center justify-between border-t pt-4">
        <button
          type="button"
          onClick={wiz.back}
          disabled={wiz.stepIndex === 0}
          className="rounded-lg border px-4 py-2 text-sm hover:bg-accent disabled:opacity-40"
        >
          {t('wizard.back', { defaultValue: 'Back' })}
        </button>
        {wiz.step !== 'review' && (
          <button
            type="button"
            onClick={wiz.next}
            disabled={!wiz.canAdvance(wiz.stepIndex)}
            className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
          >
            {t('wizard.next', { defaultValue: 'Next' })}
          </button>
        )}
      </div>
    </div>
  );
}
