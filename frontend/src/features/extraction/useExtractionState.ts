import { useState, useCallback } from 'react';
import type { ExtractionProfile, ContextFilters, CostEstimate, ExtractionProfileKind, ExtractionJobStatus } from './types';

export type WizardMode = 'single' | 'batch';

export type WizardStep = 'profile' | 'chapters' | 'confirm' | 'progress' | 'results';

const SINGLE_STEPS: WizardStep[] = ['profile', 'confirm', 'progress', 'results'];
const BATCH_STEPS: WizardStep[] = ['profile', 'chapters', 'confirm', 'progress', 'results'];

export type WizardState = {
  mode: WizardMode;
  step: WizardStep;
  stepIndex: number;
  steps: WizardStep[];
  profile: ExtractionProfile;
  chapterIds: string[];
  modelRef: string;
  maxEntitiesPerKind: number;
  contextFilters: ContextFilters;
  jobId: string | null;
  costEstimate: CostEstimate | null;
  kinds: ExtractionProfileKind[];
  selectedModelName: string;
  finalJobStatus: ExtractionJobStatus | null;
};

export function useExtractionState(mode: WizardMode, preselectedChapterIds?: string[]) {
  const steps = mode === 'single' ? SINGLE_STEPS : BATCH_STEPS;

  const [state, setState] = useState<WizardState>({
    mode,
    step: steps[0],
    stepIndex: 0,
    steps,
    profile: {},
    chapterIds: preselectedChapterIds || [],
    modelRef: '',
    maxEntitiesPerKind: 20,
    contextFilters: { alive: true, min_frequency: 2, recency_window: 100, limit: 50 },
    jobId: null,
    costEstimate: null,
    kinds: [],
    selectedModelName: '',
    finalJobStatus: null,
  });

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

  const setProfile = useCallback((profile: ExtractionProfile) => {
    setState((prev) => ({ ...prev, profile }));
  }, []);

  const setChapterIds = useCallback((chapterIds: string[]) => {
    setState((prev) => ({ ...prev, chapterIds }));
  }, []);

  const setModelRef = useCallback((modelRef: string) => {
    setState((prev) => ({ ...prev, modelRef }));
  }, []);

  const setMaxEntities = useCallback((maxEntitiesPerKind: number) => {
    setState((prev) => ({ ...prev, maxEntitiesPerKind }));
  }, []);

  const setContextFilters = useCallback((contextFilters: ContextFilters) => {
    setState((prev) => ({ ...prev, contextFilters }));
  }, []);

  const setJobId = useCallback((jobId: string, costEstimate?: CostEstimate) => {
    setState((prev) => ({ ...prev, jobId, costEstimate: costEstimate ?? prev.costEstimate }));
  }, []);

  const setKinds = useCallback((kinds: ExtractionProfileKind[]) => {
    setState((prev) => ({ ...prev, kinds }));
  }, []);

  const setSelectedModelName = useCallback((selectedModelName: string) => {
    setState((prev) => ({ ...prev, selectedModelName }));
  }, []);

  const setFinalJobStatus = useCallback((finalJobStatus: ExtractionJobStatus) => {
    setState((prev) => ({ ...prev, finalJobStatus }));
  }, []);

  /** Whether the dialog can be safely closed (not during active job) */
  const canClose = state.step !== 'progress';

  return {
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
  };
}
