import { useEffect, useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { usePdfImportState } from './usePdfImportState';
import { StepUpload } from './StepUpload';
import { StepConfigure } from './StepConfigure';
import { StepConfirm } from './StepConfirm';
import { StepProgress } from './StepProgress';
import { StepResults } from './StepResults';
import type { PdfImportStep } from './types';

// docs/specs/2026-07-06-pdf-book-import.md — mirrors
// features/extraction/ExtractionWizard.tsx's shell shape (hooks own
// logic, this component renders + wires steps), NOT
// components/import/ImportDialog.tsx's monolithic hooks+JSX pattern.

interface PdfImportWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookId: string;
  onComplete?: () => void;
}

export function PdfImportWizard({ open, onOpenChange, bookId, onComplete }: PdfImportWizardProps) {
  const { t } = useTranslation('pdf-import');
  const STEP_LABELS: Record<PdfImportStep, string> = {
    upload: t('steps.upload'),
    configure: t('steps.configure'),
    confirm: t('steps.confirm'),
    progress: t('steps.progress'),
    results: t('steps.results'),
  };
  const {
    state,
    reset,
    goNext,
    goBack,
    goToStep,
    setFile,
    setPeekResult,
    setPagesPerChunk,
    setCaptionImages,
    setModel,
    setJobId,
  } = usePdfImportState();

  const [finalStatus, setFinalStatus] = useState<'completed' | 'failed' | null>(null);
  const [finalChaptersCreated, setFinalChaptersCreated] = useState(0);
  const [finalError, setFinalError] = useState<string | undefined>(undefined);

  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (open && !wasOpenRef.current) reset();
    wasOpenRef.current = open;
  }, [open, reset]);

  if (!open) return null;

  const handleClose = () => {
    if (state.step === 'progress' && state.jobId) {
      toast.success(t('progress.backgroundToast'));
    }
    onOpenChange(false);
  };

  const chapterCount =
    state.pageCount != null ? Math.ceil(state.pageCount / Math.max(1, state.pagesPerChunk)) : 0;

  const renderStep = () => {
    switch (state.step) {
      case 'upload':
        return (
          <StepUpload
            bookId={bookId}
            file={state.file}
            pageCount={state.pageCount}
            peekError={state.peekError}
            onFileSelected={setFile}
            onPeekResult={setPeekResult}
          />
        );
      case 'configure':
        return state.pageCount != null ? (
          <StepConfigure
            pageCount={state.pageCount}
            pagesPerChunk={state.pagesPerChunk}
            captionImages={state.captionImages}
            modelRef={state.modelRef}
            onPagesPerChunkChange={setPagesPerChunk}
            onCaptionImagesChange={setCaptionImages}
            onModelChange={setModel}
          />
        ) : null;
      case 'confirm':
        return state.file && state.pageCount != null ? (
          <StepConfirm
            bookId={bookId}
            file={state.file}
            pageCount={state.pageCount}
            pagesPerChunk={state.pagesPerChunk}
            captionImages={state.captionImages}
            modelSource={state.modelSource}
            modelRef={state.modelRef}
            onJobCreated={(jobId) => {
              setJobId(jobId);
              goNext();
            }}
          />
        ) : null;
      case 'progress':
        return state.jobId ? (
          <StepProgress
            bookId={bookId}
            jobId={state.jobId}
            expectedChapters={chapterCount}
            onBackground={handleClose}
            onComplete={(status, chaptersCreated, error) => {
              setFinalStatus(status);
              setFinalChaptersCreated(chaptersCreated);
              setFinalError(error);
              goNext();
              onComplete?.();
            }}
          />
        ) : null;
      case 'results':
        return finalStatus ? (
          <StepResults
            status={finalStatus}
            chaptersCreated={finalChaptersCreated}
            error={finalError}
            onClose={handleClose}
            onRestart={reset}
          />
        ) : null;
    }
  };

  const showBackButton = state.stepIndex > 0 && state.step !== 'progress' && state.step !== 'results' && state.step !== 'confirm';
  const showNextButton = state.step === 'upload' || state.step === 'configure';
  const canNext = state.step === 'upload' ? state.peeked && state.pageCount != null : state.step === 'configure' ? true : false;

  return (
    <Dialog.Root open onOpenChange={(next) => { if (!next) handleClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border bg-background shadow-xl max-h-[85vh]">
          <div className="flex items-center justify-between border-b px-5 py-3.5 flex-shrink-0">
            <div>
              <Dialog.Title className="text-sm font-semibold">{t('title')}</Dialog.Title>
              <Dialog.Description className="text-[11px] text-muted-foreground mt-0.5">
                {t('description')}
              </Dialog.Description>
            </div>
            <button
              onClick={handleClose}
              className="p-1.5 rounded-md hover:bg-secondary text-muted-foreground transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex items-center gap-1 px-5 py-2 border-b bg-card/30 flex-shrink-0">
            {(['upload', 'configure', 'confirm', 'progress', 'results'] as PdfImportStep[]).map((step, idx) => {
              const isCurrent = idx === state.stepIndex;
              const isPast = idx < state.stepIndex;
              return (
                <div key={step} className="flex items-center gap-1">
                  {idx > 0 && <div className={cn('w-6 h-px', isPast ? 'bg-primary/50' : 'bg-border')} />}
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
                    {STEP_LABELS[step]}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">{renderStep()}</div>

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
                    onClick={() => (state.step === 'upload' ? goToStep('configure') : goNext())}
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
