import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import * as Dialog from '@radix-ui/react-dialog';
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
  const navigate = useNavigate();
  const {
    state,
    reset,
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
    setEffort,
    setFinalJobStatus,
    canClose,
  } = useExtractionState(mode, preselectedChapterIds);

  // Re-seed on reopen so a finished run doesn't leave the wizard stuck on the
  // stale results step (previously required an F5). Mirrors GlossaryTranslateWizard.
  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (open && !wasOpenRef.current) reset();
    wasOpenRef.current = open;
  }, [open, reset]);

  if (!open) return null;

  const handleClose = () => {
    if (!canClose) return;
    // Dismissing while the job is still running: it continues server-side and is
    // tracked in the unified Jobs dashboard — surface a handoff so the user can
    // monitor or cancel it there instead of being trapped in the modal.
    if (state.step === 'progress' && state.jobId) {
      toast.success(t('progress.backgroundToast'), {
        action: {
          label: t('progress.viewInJobs'),
          onClick: () => navigate('/jobs'),
        },
      });
    }
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
            effort={state.effort}
            onProfileChange={setProfile}
            onModelChange={setModelRef}
            onEffortChange={setEffort}
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
            effort={state.effort}
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
            onBackground={handleClose}
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

  const showBackButton = state.stepIndex > 0 && state.step !== 'progress' && state.step !== 'results' && state.step !== 'confirm';
  const showNextButton = state.step === 'profile' || state.step === 'chapters';
  const canNext =
    state.step === 'profile' ? canProceedFromProfile :
    state.step === 'chapters' ? state.chapterIds.length > 0 :
    false;

  // DOCK-9 (docs/standards/dockable-gui.md): raw Dialog.* primitives, not FormDialog —
  // the step-indicator bar between header and body, plus a footer whose buttons vary
  // per step (back/cancel/next), don't fit FormDialog's fixed title+body+footer
  // template (same rationale as EntityEditorModal's meta-bar/tab-bar chrome). `open`
  // is passed as the literal `true` here (we've already early-returned above when the
  // prop is false) — dismissal is entirely parent-driven: Escape/outside-click/the X
  // button all route through `onOpenChange` → `handleClose` → the caller's
  // `onOpenChange(false)`, which unmounts this subtree on the next render.
  return (
    <Dialog.Root open onOpenChange={(next) => { if (!next) handleClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border bg-background shadow-xl max-h-[85vh]">
          {/* Header */}
          <div className="flex items-center justify-between border-b px-5 py-3.5 flex-shrink-0">
            <div>
              <Dialog.Title className="text-sm font-semibold">{t('title')}</Dialog.Title>
              <Dialog.Description className="text-[11px] text-muted-foreground mt-0.5">{t('subtitle')}</Dialog.Description>
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

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-5 py-4">
            {renderStep()}
          </div>

          {/* Footer */}
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
                    disabled={!canNext}
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
