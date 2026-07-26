// C24 (dị bản M0) — Divergence wizard CONTROLLER (the "controller" in React-MVC:
// owns ALL step state + logic, no JSX). Drives a 4-step flow that ends in
// POST /works/{id}/derive:
//   Step 1 — source Work (given) + branch_point (chapter-level, G3)
//   Step 2 — divergence type (UX §7.1: pov_shift · character_transform · au)
//   Step 3 — overrides preview (entity-field overrides + added canon rules, editable)
//   Step 4 — name → submit
//
// FE-rule compliance (CLAUDE.md / adversary focus):
//  • step transitions are EXPLICIT callbacks (goNext/goBack/goTo) — NEVER a
//    useEffect(()=>{...},[step]). There is no useEffect in this hook at all.
//  • the hook is self-contained — it owns its state + the derive mutation; the
//    view renders only.
//  • no localStorage — server is SSOT; the wizard holds transient draft state only
//    until submit, then the derive response (with the derivative project_id) is the
//    persisted truth.
import { useCallback, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import { derivativeContextKey } from './useDerivativeContext';
import type { DeriveBody, DivergenceTaxonomy, EntityOverride, Work } from '../types';

export type WizardStep = 1 | 2 | 3 | 4;

/** The mutable per-entity override draft the Step-3 editor manipulates. We keep a
 *  flat map keyed by target_entity_id so toggling/editing one entity is O(1) and
 *  the OVERRIDDEN set the studio reads later (DPS2) is exactly this map's keys. */
export type OverrideDraft = Record<string, Record<string, unknown>>;

export type UseDivergenceWizardArgs = {
  /** The SOURCE Work the derivative diverges from. Its project_id is the derive
   *  path key (C23 route). */
  sourceWork: Work;
  token: string | null;
  /** Called with the freshly-spawned DERIVATIVE Work after a successful derive —
   *  the caller routes into / opens the dị bản studio. */
  onDerived?: (derivative: Work) => void;
};

export type UseDivergenceWizard = {
  step: WizardStep;
  // Step 1
  branchPoint: number | null;
  setBranchPoint: (n: number | null) => void;
  // Step 2
  taxonomy: DivergenceTaxonomy;
  setTaxonomy: (t: DivergenceTaxonomy) => void;
  povAnchor: string | null;
  setPovAnchor: (id: string | null) => void;
  // Step 3
  overrides: OverrideDraft;
  /** Set (or clear, when fields is empty/null) the entity-field override for one
   *  entity. Clearing removes the key so it drops OUT of the OVERRIDDEN set. */
  setOverride: (entityId: string, fields: Record<string, unknown> | null) => void;
  canonRules: string[];
  setCanonRules: (rules: string[]) => void;
  // Step 4
  name: string;
  setName: (s: string) => void;
  // Navigation (explicit callbacks — no useEffect-for-events)
  goNext: () => void;
  goBack: () => void;
  goTo: (s: WizardStep) => void;
  canAdvance: boolean;
  // Submit
  submit: () => void;
  isSubmitting: boolean;
  error: string | null;
  /** The derive body the wizard WILL submit — exposed so a test can assert the
   *  taxonomy→spec + override mapping without driving the network. */
  buildBody: () => DeriveBody;
};

const STEP_MIN: WizardStep = 1;
const STEP_MAX: WizardStep = 4;

export function useDivergenceWizard({
  sourceWork,
  token,
  onDerived,
}: UseDivergenceWizardArgs): UseDivergenceWizard {
  const qc = useQueryClient();
  const [step, setStep] = useState<WizardStep>(1);
  const [branchPoint, setBranchPoint] = useState<number | null>(null);
  const [taxonomy, setTaxonomy] = useState<DivergenceTaxonomy>('au');
  const [povAnchor, setPovAnchor] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<OverrideDraft>({});
  const [canonRules, setCanonRules] = useState<string[]>([]);
  const [name, setName] = useState('');

  const setOverride = useCallback(
    (entityId: string, fields: Record<string, unknown> | null) => {
      setOverrides((prev) => {
        const next = { ...prev };
        if (!fields || Object.keys(fields).length === 0) {
          delete next[entityId]; // clearing drops it from the OVERRIDDEN set
        } else {
          next[entityId] = fields;
        }
        return next;
      });
    },
    [],
  );

  const buildBody = useCallback((): DeriveBody => {
    const entity_overrides: EntityOverride[] = Object.entries(overrides).map(
      ([target_entity_id, overridden_fields]) => ({ target_entity_id, overridden_fields }),
    );
    return {
      // BE-13a — send the name the wizard collected (previously dropped here, so every
      // derivative was unnamed). submit() already gates on name.trim().length > 0.
      name: name.trim(),
      branch_point: branchPoint,
      divergence: {
        taxonomy,
        // pov_anchor is only meaningful for a POV shift; carry it generally but it
        // is optional server-side.
        pov_anchor: povAnchor,
        canon_rule: canonRules.map((r) => r.trim()).filter(Boolean),
      },
      entity_overrides,
    };
  }, [name, branchPoint, taxonomy, povAnchor, canonRules, overrides]);

  const derive = useMutation({
    mutationFn: () => compositionApi.deriveWork(sourceWork.project_id, buildBody(), token!),
    onSuccess: (derivative) => {
      // The derivative is a fresh Work for the SAME book — bust the work-resolution
      // cache so a re-resolve sees the new candidate. WS-B2: the studio badges now
      // read the DURABLE spec via GET /works/{id}/derivative-context (persisted in
      // the same txn as the derive), so we just invalidate that key — no ephemeral
      // override-id stash. The next read of the derivative returns real state.
      if (derivative.project_id) {
        qc.invalidateQueries({ queryKey: derivativeContextKey(derivative.project_id) });
      }
      qc.invalidateQueries({ queryKey: ['composition', 'work', sourceWork.book_id] });
      onDerived?.(derivative);
    },
  });

  // Step-gating: each step has a minimal precondition to advance. Derived (no
  // effect) so the Next button reflects it without a sync hazard.
  const canAdvance = useMemo(() => {
    switch (step) {
      case 1:
        return true; // branch_point optional (null = diverge from the start)
      case 2:
        return true; // a taxonomy is always selected (defaults to 'au')
      case 3:
        return true; // overrides + canon rules are optional in M0
      case 4:
        return name.trim().length > 0;
      default:
        return false;
    }
  }, [step, name]);

  const goTo = useCallback((s: WizardStep) => {
    if (s >= STEP_MIN && s <= STEP_MAX) setStep(s);
  }, []);
  const goNext = useCallback(() => {
    setStep((s) => (s < STEP_MAX ? ((s + 1) as WizardStep) : s));
  }, []);
  const goBack = useCallback(() => {
    setStep((s) => (s > STEP_MIN ? ((s - 1) as WizardStep) : s));
  }, []);

  // The submit is an EXPLICIT action handler (called from the Step-4 button), not a
  // reaction to reaching step 4.
  const submit = useCallback(() => {
    if (!token || name.trim().length === 0) return;
    derive.mutate();
  }, [token, name, derive]);

  return {
    step,
    branchPoint,
    setBranchPoint,
    taxonomy,
    setTaxonomy,
    povAnchor,
    setPovAnchor,
    overrides,
    setOverride,
    canonRules,
    setCanonRules,
    name,
    setName,
    goNext,
    goBack,
    goTo,
    canAdvance,
    submit,
    isSubmitting: derive.isPending,
    error: derive.isError ? (derive.error as Error)?.message ?? 'derive failed' : null,
    buildBody,
  };
}
