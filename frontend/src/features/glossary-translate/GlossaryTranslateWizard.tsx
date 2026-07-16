import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import * as Dialog from '@radix-ui/react-dialog';
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
  const navigate = useNavigate();
  const {
    state,
    goNext,
    goBack,
    goToStep,
    setTargetLanguage,
    setOverwriteMode,
    setModelRef,
    setSelectedModelName,
    setEffort,
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

  // S12: "View glossary" used to just close the wizard (navigated nowhere). Take the user to the
  // book's glossary — the whole point of the affordance after a batch translate.
  const handleViewGlossary = () => {
    if (!canClose) return;
    onOpenChange(false);
    navigate(`/books/${bookId}/glossary`);
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
            effort={state.effort}
            sourceLanguage={bookOriginalLanguage}
            onTargetLanguageChange={setTargetLanguage}
            onOverwriteModeChange={setOverwriteMode}
            onModelChange={setModelRef}
            onModelNameChange={setSelectedModelName}
            onEffortChange={setEffort}
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
            effort={state.effort}
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
            onViewGlossary={handleViewGlossary}
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

  // Custom multi-part chrome (title block + a separate always-visible step-indicator row that
  // must stay pinned above the scrollable body) doesn't fit FormDialog's fixed title+body+footer
  // template, so this uses raw Dialog.* primitives directly (docs/standards/dockable-gui.md
  // DOCK-9 "custom chrome" branch — same precedent as EntityEditorModal). Radix's built-in
  // Escape/outside-click dismissal routes through `handleClose`, which already no-ops while
  // `!canClose` (e.g. mid-`progress` step) — same guard the old hand-rolled backdrop honored.
  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!next) handleClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border bg-background shadow-xl max-h-[85vh]">
          <div className="flex items-center justify-between border-b px-5 py-3.5 flex-shrink-0">
            <div>
              <Dialog.Title className="text-sm font-semibold">{t('title')}</Dialog.Title>
              <Dialog.Description className="text-[11px] text-muted-foreground mt-0.5">
                {t('subtitle')}
              </Dialog.Description>
            </div>
            {canClose && (
              <Dialog.Close asChild>
                <button
                  className="p-1.5 rounded-md hover:bg-secondary text-muted-foreground transition-colors"
                  aria-label={t('button.cancel')}
                >
                  <X className="h-4 w-4" />
                </button>
              </Dialog.Close>
            )}
          </div>

          <div className="flex items-center gap-1 px-5 py-2 border-b bg-card/30 flex-shrink-0">
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

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{renderStep()}</div>

          {sameLanguage && state.step === 'config' && (
            <p className="px-5 pb-2 text-[10px] text-destructive flex-shrink-0">
              {t('config.sameLanguageError')}
            </p>
          )}

          {(showBackButton || showNextButton) && (
            <div className="flex items-center justify-between border-t px-5 py-3 flex-shrink-0">
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
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
