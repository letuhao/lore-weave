import { useCallback, useMemo, useState } from 'react';
import {
  MODEL_ROLES,
  type CreateCampaignPayload,
  type EstimateRequest,
  type ModelRole,
} from '../types';

// Wizard steps (the final step's action is Launch).
export const WIZARD_STEPS = ['bookProject', 'range', 'models', 'review'] as const;
export type WizardStep = (typeof WIZARD_STEPS)[number];

export interface WizardForm {
  name: string;
  bookId: string | null;
  projectId: string | null;
  targetLanguage: string;
  chapterFrom: number | null;
  chapterTo: number | null;
  gatingMode: 'phase_barrier' | 'cold_start';  // D-S5C-GATING (quality vs speed)
  budgetUsd: string;                 // free-text USD ('' = uncapped)
  // G1 — captured from the last successful /estimate so the launch persists the
  // band for the completion report's spent-vs-estimate (null = never estimated).
  estUsdLow: string | null;
  estUsdHigh: string | null;
  picks: Record<ModelRole, string | null>;  // user_model_id per role (null = unset)
  confirmEmbeddingChange: boolean;
}

const EMPTY_PICKS = MODEL_ROLES.reduce(
  (acc, r) => ({ ...acc, [r]: null }),
  {} as Record<ModelRole, string | null>,
);

const INITIAL: WizardForm = {
  name: '',
  bookId: null,
  projectId: null,
  targetLanguage: '',
  chapterFrom: null,
  chapterTo: null,
  gatingMode: 'phase_barrier',  // highest quality default (decision B)
  budgetUsd: '',
  estUsdLow: null,
  estUsdHigh: null,
  picks: { ...EMPTY_PICKS },
  confirmEmbeddingChange: false,
};

/** Map a role's user_model_id pick → a {model_source, model_ref} pair (BYOK
 *  user_model space; null/null when unset). */
function pickPair(ref: string | null) {
  return ref
    ? { model_source: 'user_model', model_ref: ref }
    : { model_source: null, model_ref: null };
}

/**
 * Controller for the Auto-Draft Factory setup wizard (S5c). Owns step index +
 * the whole form + the payload assembly; the step components are pure views that
 * read this and call its setters. Self-contained (no parent useEffect lifecycle).
 */
export function useCampaignWizard() {
  const [stepIndex, setStepIndex] = useState(0);
  const [form, setForm] = useState<WizardForm>(INITIAL);

  const setField = useCallback(
    <K extends keyof WizardForm>(key: K, value: WizardForm[K]) =>
      setForm((f) => ({ ...f, [key]: value })),
    [],
  );

  const setPick = useCallback(
    (role: ModelRole, ref: string | null) =>
      setForm((f) => ({ ...f, picks: { ...f.picks, [role]: ref } })),
    [],
  );

  // Per-step gating. Required: name/book/project (step 0) and translator+extractor
  // models (step 2) — without those the campaign's stages 422 on dispatch. Range,
  // verifier, eval-judge, embedding, reranker are optional (backend fallbacks).
  const canAdvance = useCallback(
    (step: number): boolean => {
      if (step === 0) {
        return !!form.name.trim() && !!form.bookId && !!form.projectId;
      }
      if (step === 1) {
        const { chapterFrom: lo, chapterTo: hi } = form;
        return lo === null || hi === null || lo <= hi;
      }
      if (step === 2) {
        return !!form.picks.translator && !!form.picks.extractor;
      }
      return true;
    },
    [form],
  );

  const next = useCallback(
    () => setStepIndex((i) => Math.min(i + 1, WIZARD_STEPS.length - 1)),
    [],
  );
  const back = useCallback(() => setStepIndex((i) => Math.max(i - 1, 0)), []);

  const buildEstimateRequest = useCallback((): EstimateRequest => {
    const models: EstimateRequest['models'] = {};
    for (const role of MODEL_ROLES) {
      if (form.picks[role]) models[role] = pickPair(form.picks[role]);
    }
    return {
      book_id: form.bookId!,
      chapter_from: form.chapterFrom,
      chapter_to: form.chapterTo,
      target_language: form.targetLanguage || null,
      models,
    };
  }, [form]);

  const buildCreatePayload = useCallback((): CreateCampaignPayload => {
    const ex = pickPair(form.picks.extractor);
    const tr = pickPair(form.picks.translator);
    const ve = pickPair(form.picks.verifier);
    const ej = pickPair(form.picks.eval_judge);
    const em = pickPair(form.picks.embedding);
    const rr = pickPair(form.picks.reranker);
    const budget = form.budgetUsd.trim();
    return {
      book_id: form.bookId!,
      name: form.name.trim(),
      knowledge_project_id: form.projectId!,
      target_language: form.targetLanguage || null,
      gating_mode: form.gatingMode,  // D-S5C-GATING
      chapter_from: form.chapterFrom,
      chapter_to: form.chapterTo,
      budget_usd: budget ? budget : null,
      knowledge_model_source: ex.model_source,
      knowledge_model_ref: ex.model_ref,
      translation_model_source: tr.model_source,
      translation_model_ref: tr.model_ref,
      verifier_model_source: ve.model_source,
      verifier_model_ref: ve.model_ref,
      eval_judge_model_source: ej.model_source,
      eval_judge_model_ref: ej.model_ref,
      embedding_model_source: em.model_source,
      embedding_model_ref: em.model_ref,
      rerank_model_source: rr.model_source,
      rerank_model_ref: rr.model_ref,
      confirm_embedding_change: form.confirmEmbeddingChange,
      est_usd_low: form.estUsdLow,   // G1 (persist the estimate band for the report)
      est_usd_high: form.estUsdHigh,
    };
  }, [form]);

  const step = WIZARD_STEPS[stepIndex];
  return useMemo(
    () => ({
      step, stepIndex, totalSteps: WIZARD_STEPS.length,
      form, setField, setPick,
      canAdvance, next, back,
      buildEstimateRequest, buildCreatePayload,
    }),
    [step, stepIndex, form, setField, setPick, canAdvance, next, back, buildEstimateRequest, buildCreatePayload],
  );
}
