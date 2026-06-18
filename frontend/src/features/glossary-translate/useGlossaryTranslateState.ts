import { useState, useCallback } from 'react';
import type {
  OverwriteMode,
  GlossaryTranslateCostEstimate,
  GlossaryTranslateJobStatus,
} from './types';

export type WizardStep = 'config' | 'confirm' | 'progress' | 'results';

const STEPS: WizardStep[] = ['config', 'confirm', 'progress', 'results'];

function initialState(defaultTargetLanguage: string): WizardState {
  return {
    step: STEPS[0],
    stepIndex: 0,
    steps: STEPS,
    targetLanguage: defaultTargetLanguage,
    overwriteMode: 'missing_only',
    modelRef: '',
    selectedModelName: '',
    thinkingEnabled: false,
    jobId: null,
    costEstimate: null,
    totalEntities: 0,
    finalJobStatus: null,
  };
}

export type WizardState = {
  step: WizardStep;
  stepIndex: number;
  steps: WizardStep[];
  targetLanguage: string;
  overwriteMode: OverwriteMode;
  modelRef: string;
  selectedModelName: string;
  thinkingEnabled: boolean;
  jobId: string | null;
  costEstimate: GlossaryTranslateCostEstimate | null;
  totalEntities: number;
  finalJobStatus: GlossaryTranslateJobStatus | null;
};

export function useGlossaryTranslateState(defaultTargetLanguage = 'vi') {
  const [state, setState] = useState<WizardState>(() => initialState(defaultTargetLanguage));

  const reset = useCallback(() => {
    setState(initialState(defaultTargetLanguage));
  }, [defaultTargetLanguage]);

  const goNext = useCallback(() => {
    setState((prev) => {
      const nextIdx = Math.min(prev.stepIndex + 1, prev.steps.length - 1);
      return { ...prev, stepIndex: nextIdx, step: prev.steps[nextIdx] };
    });
  }, []);

  const goBack = useCallback(() => {
    setState((prev) => {
      const prevIdx = Math.max(prev.stepIndex - 1, 0);
      return { ...prev, stepIndex: prevIdx, step: prev.steps[prevIdx] };
    });
  }, []);

  const goToStep = useCallback((step: WizardStep) => {
    setState((prev) => {
      const idx = prev.steps.indexOf(step);
      if (idx === -1) return prev;
      return { ...prev, stepIndex: idx, step };
    });
  }, []);

  const setTargetLanguage = useCallback((targetLanguage: string) => {
    setState((prev) => ({ ...prev, targetLanguage }));
  }, []);

  const setOverwriteMode = useCallback((overwriteMode: OverwriteMode) => {
    setState((prev) => ({ ...prev, overwriteMode }));
  }, []);

  const setModelRef = useCallback((modelRef: string) => {
    setState((prev) => ({ ...prev, modelRef }));
  }, []);

  const setSelectedModelName = useCallback((selectedModelName: string) => {
    setState((prev) => ({ ...prev, selectedModelName }));
  }, []);

  const setThinkingEnabled = useCallback((thinkingEnabled: boolean) => {
    setState((prev) => ({ ...prev, thinkingEnabled }));
  }, []);

  const setJobCreated = useCallback(
    (jobId: string, totalEntities: number, costEstimate: GlossaryTranslateCostEstimate) => {
      setState((prev) => ({
        ...prev,
        jobId,
        totalEntities,
        costEstimate,
      }));
    },
    [],
  );

  const setFinalJobStatus = useCallback((finalJobStatus: GlossaryTranslateJobStatus) => {
    setState((prev) => ({ ...prev, finalJobStatus }));
  }, []);

  const canClose = state.step !== 'progress';

  return {
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
  };
}

/** True when target equals book source (batch translate would be a no-op). */
export function isSameLanguageTarget(sourceLanguage: string | undefined, targetLanguage: string): boolean {
  if (!sourceLanguage?.trim()) return false;
  return sourceLanguage.trim() === targetLanguage.trim();
}
