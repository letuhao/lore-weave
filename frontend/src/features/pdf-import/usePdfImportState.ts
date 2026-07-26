import { useCallback, useState } from 'react';
import type { PdfImportState, PdfImportStep } from './types';
import { PDF_IMPORT_STEPS } from './types';

// docs/specs/2026-07-06-pdf-book-import.md — mirrors
// features/extraction/useExtractionState.ts's step-machine shape
// (goNext/goBack/goToStep over a fixed step array), not
// components/import/ImportDialog.tsx's inlined useState pile.

const DEFAULT_PAGES_PER_CHUNK = 5;

function initialState(): PdfImportState {
  return {
    step: PDF_IMPORT_STEPS[0],
    stepIndex: 0,
    file: null,
    pageCount: null,
    peeked: false,
    peekError: null,
    pagesPerChunk: DEFAULT_PAGES_PER_CHUNK,
    captionImages: false,
    modelSource: null,
    modelRef: null,
    jobId: null,
  };
}

export function usePdfImportState() {
  const [state, setState] = useState<PdfImportState>(initialState);

  const reset = useCallback(() => setState(initialState()), []);

  const goNext = useCallback(() => {
    setState((prev) => {
      const nextIdx = Math.min(prev.stepIndex + 1, PDF_IMPORT_STEPS.length - 1);
      return { ...prev, stepIndex: nextIdx, step: PDF_IMPORT_STEPS[nextIdx] };
    });
  }, []);

  const goBack = useCallback(() => {
    setState((prev) => {
      const prevIdx = Math.max(prev.stepIndex - 1, 0);
      return { ...prev, stepIndex: prevIdx, step: PDF_IMPORT_STEPS[prevIdx] };
    });
  }, []);

  const goToStep = useCallback((step: PdfImportStep) => {
    setState((prev) => {
      const idx = PDF_IMPORT_STEPS.indexOf(step);
      if (idx === -1) return prev;
      return { ...prev, stepIndex: idx, step };
    });
  }, []);

  const setFile = useCallback((file: File | null) => {
    setState((prev) => ({ ...prev, file, pageCount: null, peeked: false, peekError: null }));
  }, []);

  const setPeekResult = useCallback((pageCount: number | null, error: string | null) => {
    setState((prev) => ({ ...prev, pageCount, peeked: error === null, peekError: error }));
  }, []);

  const setPagesPerChunk = useCallback((pagesPerChunk: number) => {
    setState((prev) => ({ ...prev, pagesPerChunk: Math.max(1, Math.floor(pagesPerChunk) || 1) }));
  }, []);

  const setCaptionImages = useCallback((captionImages: boolean) => {
    setState((prev) => ({ ...prev, captionImages }));
  }, []);

  const setModel = useCallback((modelSource: string | null, modelRef: string | null) => {
    setState((prev) => ({ ...prev, modelSource, modelRef }));
  }, []);

  const setJobId = useCallback((jobId: string) => {
    setState((prev) => ({ ...prev, jobId }));
  }, []);

  return {
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
  };
}
