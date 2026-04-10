import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { useExtractionState, type WizardMode, type WizardStep } from './useExtractionState';
import { StepProfile } from './StepProfile';
import { StepBatchConfig } from './StepBatchConfig';
import { StepConfirm } from './StepConfirm';
import { StepProgress } from './StepProgress';
import { StepResults } from './StepResults';
import { cn } from '@/lib/utils';
import type { ExtractionProfileKind, CostEstimate } from './types';

interface ExtractionWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookId: string;
  mode: WizardMode;
  preselectedChapterIds?: string[];
  onComplete?: () => void;
}

const STEP_LABELS: Record<WizardStep, string> = {
  profile: 'steps.profile',
  chapters: 'steps.chapters',
  confirm: 'steps.confirm',
  progress: 'steps.progress',
  results: 'steps.results',
};

export function ExtractionWizard({
  open,
  onOpenChange,
  bookId,
  mode,
  preselectedChapterIds,
  onComplete,
}: ExtractionWizardProps) {
  const { t } = useTranslation('extraction');
  const {
    state,
    goNext,
    goBack,
    goToStep,
    setProfile,
    setChapterIds,
    setModelRef,
    setMaxEntities,
    setContextFilters,
    setJobId,
    setKinds,
    setSelectedModelName,
    setFinalJobStatus,
    canClose,
  } = useExtractionState(mode, preselectedChapterIds);

  if (!open) return null;

  const handleClose = () => {
    if (!canClose) return;
    onOpenChange(false);
  };

  const enabledKindsCount = Object.keys(state.profile).length;
  const canProceedFromProfile = enabledKindsCount > 0 && !!state.modelRef;

  const renderStep = () => {
    switch (state.step) {
      case 'profile':
        return (
          <StepProfile
            bookId={bookId}
            profile={state.profile}
            modelRef={state.modelRef}
            onProfileChange={setProfile}
            onModelChange={setModelRef}
            onKindsLoaded={setKinds}
            onModelNameChange={setSelectedModelName}
            onClose={handleClose}
          />
        );
      case 'chapters':
        return (
          <StepBatchConfig
            bookId={bookId}
            chapterIds={state.chapterIds}
            contextFilters={state.contextFilters}
            maxEntitiesPerKind={state.maxEntitiesPerKind}
            onChapterIdsChange={setChapterIds}
            onContextFiltersChange={setContextFilters}
            onMaxEntitiesChange={setMaxEntities}
          />
        );
      case 'confirm':
        return (
          <StepConfirm
            bookId={bookId}
            profile={state.profile}
            chapterIds={state.chapterIds}
            modelRef={state.modelRef}
            maxEntitiesPerKind={state.maxEntitiesPerKind}
            contextFilters={state.contextFilters}
            kinds={state.kinds}
            selectedModelName={state.selectedModelName}
            onJobCreated={(jobId, costEstimate) => {
              setJobId(jobId, costEstimate);
              goNext();
            }}
            onEditProfile={() => goToStep('profile')}
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
          />
        ) : null;
    }
  };

  const showBackButton = state.stepIndex > 0 && state.step !== 'progress' && state.step !== 'results' && state.step !== 'confirm';
  const showNextButton = state.step === 'profile' || state.step === 'chapters';
  const canNext =
    state.step === 'profile' ? canProceedFromProfile :
    state.step === 'chapters' ? state.chapterIds.length > 0 :
    false;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-50 bg-black/50" onClick={handleClose} />

      {/* Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-3xl rounded-lg border bg-background shadow-xl flex flex-col max-h-[85vh]"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
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

          {/* Step indicator */}
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

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-5 py-4">
            {renderStep()}
          </div>

          {/* Footer */}
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
                    disabled={!canNext}
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
