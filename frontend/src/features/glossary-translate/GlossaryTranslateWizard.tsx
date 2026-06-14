import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import {
  useGlossaryTranslateState,
  isSameLanguageTarget,
  type WizardStep,
} from './useGlossaryTranslateState';
import { StepConfig } from './StepConfig';
import { StepConfirm } from './StepConfirm';
import { StepProgress } from './StepProgress';
import { StepResults } from './StepResults';
import { cn } from '@/lib/utils';

interface GlossaryTranslateWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookId: string;
  bookOriginalLanguage?: string;
  onComplete?: () => void;
}

const STEP_LABELS: Record<WizardStep, string> = {
  config: 'steps.config',
  confirm: 'steps.confirm',
  progress: 'steps.progress',
  results: 'steps.results',
};

export function GlossaryTranslateWizard({
  open,
  onOpenChange,
  bookId,
  bookOriginalLanguage,
  onComplete,
}: GlossaryTranslateWizardProps) {
  const { t } = useTranslation('glossaryTranslate');
  const {
    state,
    goNext,
    goBack,
    goToStep,
    setTargetLanguage,
    setOverwriteMode,
    setModelRef,
    setSelectedModelName,
    setThinkingEnabled,
    setJobCreated,
    setFinalJobStatus,
    reset,
    canClose,
  } = useGlossaryTranslateState();

  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (open && !wasOpenRef.current) {
      reset();
    }
    wasOpenRef.current = open;
  }, [open, reset]);

  if (!open) return null;

  const handleClose = () => {
    if (!canClose) return;
    onOpenChange(false);
  };

  const sameLanguage = isSameLanguageTarget(bookOriginalLanguage, state.targetLanguage);
  const canProceedFromConfig = !!state.modelRef && !!state.targetLanguage && !sameLanguage;

  const renderStep = () => {
    switch (state.step) {
      case 'config':
        return (
          <StepConfig
            targetLanguage={state.targetLanguage}
            overwriteMode={state.overwriteMode}
            modelRef={state.modelRef}
            thinkingEnabled={state.thinkingEnabled}
            sourceLanguage={bookOriginalLanguage}
            onTargetLanguageChange={setTargetLanguage}
            onOverwriteModeChange={setOverwriteMode}
            onModelChange={setModelRef}
            onModelNameChange={setSelectedModelName}
            onThinkingEnabledChange={setThinkingEnabled}
          />
        );
      case 'confirm':
        return (
          <StepConfirm
            bookId={bookId}
            targetLanguage={state.targetLanguage}
            overwriteMode={state.overwriteMode}
            modelRef={state.modelRef}
            selectedModelName={state.selectedModelName}
            thinkingEnabled={state.thinkingEnabled}
            sourceLanguage={bookOriginalLanguage}
            onJobCreated={(jobId, totalEntities, costEstimate) => {
              setJobCreated(jobId, totalEntities, costEstimate);
              goToStep('progress');
            }}
            onEditConfig={() => goToStep('config')}
          />
        );
      case 'progress':
        return state.jobId ? (
          <StepProgress
            jobId={state.jobId}
            onComplete={(finalStatus) => {
              setFinalJobStatus(finalStatus);
              goNext();
              onComplete?.();
            }}
          />
        ) : null;
      case 'results':
        return state.finalJobStatus ? (
          <StepResults
            jobStatus={state.finalJobStatus}
            costEstimate={state.costEstimate}
            onClose={handleClose}
            onViewGlossary={handleClose}
            onRestart={reset}
          />
        ) : null;
    }
  };

  const showBackButton =
    state.stepIndex > 0 &&
    state.step !== 'progress' &&
    state.step !== 'results' &&
    state.step !== 'confirm';
  const showNextButton = state.step === 'config';

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50" onClick={handleClose} />

      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-2xl rounded-lg border bg-background shadow-xl flex flex-col max-h-[85vh]"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b px-5 py-3.5">
            <div>
              <h2 className="text-sm font-semibold">{t('title')}</h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">{t('subtitle')}</p>
            </div>
            {canClose && (
              <button
                onClick={handleClose}
                className="p-1.5 rounded-md hover:bg-secondary text-muted-foreground transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-1 px-5 py-2 border-b bg-card/30">
            {state.steps.map((step, idx) => {
              const isCurrent = idx === state.stepIndex;
              const isPast = idx < state.stepIndex;
              return (
                <div key={step} className="flex items-center gap-1">
                  {idx > 0 && (
                    <div className={cn('w-6 h-px', isPast ? 'bg-primary/50' : 'bg-border')} />
                  )}
                  <div
                    className={cn(
                      'flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium transition-colors',
                      isCurrent && 'bg-primary/10 text-primary',
                      isPast && 'text-muted-foreground',
                      !isCurrent && !isPast && 'text-muted-foreground/50',
                    )}
                  >
                    <span
                      className={cn(
                        'w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold',
                        isCurrent && 'bg-primary text-primary-foreground',
                        isPast && 'bg-muted-foreground/30 text-muted-foreground',
                        !isCurrent && !isPast && 'bg-border text-muted-foreground/50',
                      )}
                    >
                      {isPast ? '✓' : idx + 1}
                    </span>
                    {t(STEP_LABELS[step])}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">{renderStep()}</div>

          {sameLanguage && state.step === 'config' && (
            <p className="px-5 pb-2 text-[10px] text-destructive">{t('config.sameLanguageError')}</p>
          )}

          {(showBackButton || showNextButton) && (
            <div className="flex items-center justify-between border-t px-5 py-3">
              <div>
                {showBackButton && (
                  <button
                    onClick={goBack}
                    className="rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                  >
                    {t('button.back')}
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleClose}
                  className="rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                >
                  {t('button.cancel')}
                </button>
                {showNextButton && (
                  <button
                    onClick={goNext}
                    disabled={!canProceedFromConfig}
                    className="rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {t('button.next')}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
