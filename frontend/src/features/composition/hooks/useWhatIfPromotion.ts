// C27 (dị bản M4) — what-if → derivative PROMOTION controller (React-MVC "controller":
// owns the logic, no JSX). A "what-if" is an EPHEMERAL exploration the writer toys
// with (a branch_point + divergence type + entity overrides + canon rules held in
// memory, NOT yet persisted — no project_id, no Work row). PROMOTING it materializes
// it into a PERSISTENT derivative Work through the C23 derive path
// (POST /works/{id}/derive), which:
//   • mints the derivative its OWN FRESH knowledge project_id (G2 — never reuses an
//     existing/the source project_id),
//   • persists the divergence_spec (taxonomy + pov_anchor + canon_rule[]) and the
//     entity_override[] — CARRIED OVER from the ephemeral what-if, NONE dropped.
//
// This hook is the explicit ephemeral→persistent seam. It does NOT re-implement the
// derive call shape — it builds the SAME DeriveBody the C24 wizard submits and routes
// it through `compositionApi.deriveWork` (the one C23 path), so promotion and the
// wizard can never drift.
//
// FE-rule compliance: explicit `promote()` callback (NO useEffect-for-events); the
// hook owns its mutation + its ephemeral draft; no localStorage (a what-if is
// transient until promoted, then the derive response is the persisted truth).
import { useCallback, useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import { derivativeContextKey } from './useDerivativeContext';
import type { DeriveBody, DivergenceTaxonomy, EntityOverride, Work } from '../types';

/** The EPHEMERAL what-if exploration — the in-memory delta the writer is toying with
 *  before deciding to save it. Shape mirrors the derive inputs so promotion carries
 *  every field through with no lossy mapping. */
export type WhatIfDraft = {
  branchPoint: number | null;
  taxonomy: DivergenceTaxonomy;
  povAnchor: string | null;
  canonRules: string[];
  /** entity_id → field→value override delta (the OVERRIDDEN set). */
  overrides: Record<string, Record<string, unknown>>;
  name: string;
};

export type UseWhatIfPromotionArgs = {
  /** The SOURCE (canon) Work the what-if branches from. Its project_id is the C23
   *  derive route key; the derivative gets a DISTINCT fresh project (G2). */
  sourceWork: Work;
  /** The ephemeral what-if to promote. */
  draft: WhatIfDraft;
  token: string | null;
  /** Called with the freshly-materialized PERSISTENT derivative Work on success. */
  onPromoted?: (derivative: Work) => void;
};

export type UseWhatIfPromotion = {
  /** Build the DeriveBody the promotion WILL submit — exposed so a test (and the
   *  view) can assert spec + overrides carry over with nothing dropped. */
  buildDeriveBody: () => DeriveBody;
  /** Explicit promote action (NOT a reaction-to-state). No-op without a token/name. */
  promote: () => void;
  isPromoting: boolean;
  error: string | null;
  /** Whether the draft is promotable (a saved dị bản needs a name). */
  canPromote: boolean;
};

/** Pure: map an ephemeral what-if draft → the C23 DeriveBody, carrying EVERY field.
 *  Exported so the view + tests share the exact mapping (no drift, none dropped). */
export function whatIfToDeriveBody(draft: WhatIfDraft): DeriveBody {
  const entity_overrides: EntityOverride[] = Object.entries(draft.overrides).map(
    ([target_entity_id, overridden_fields]) => ({ target_entity_id, overridden_fields }),
  );
  return {
    branch_point: draft.branchPoint,
    divergence: {
      taxonomy: draft.taxonomy,
      pov_anchor: draft.povAnchor,
      canon_rule: draft.canonRules.map((r) => r.trim()).filter(Boolean),
    },
    entity_overrides,
  };
}

export function useWhatIfPromotion({
  sourceWork,
  draft,
  token,
  onPromoted,
}: UseWhatIfPromotionArgs): UseWhatIfPromotion {
  const qc = useQueryClient();

  const buildDeriveBody = useCallback(() => whatIfToDeriveBody(draft), [draft]);

  const promotion = useMutation({
    mutationFn: () => compositionApi.deriveWork(sourceWork.project_id, buildDeriveBody(), token!),
    onSuccess: (derivative) => {
      // The C23 derive minted a FRESH project_id — assert it diverged from the
      // source (G2). If a backend regression ever reused the source project, this
      // surfaces it instead of silently anchoring the what-if onto canon.
      if (derivative.project_id && derivative.project_id === sourceWork.project_id) {
        throw new Error('promotion reused the source project_id (expected a fresh derivative project)');
      }
      if (derivative.project_id) {
        // WS-B2: the studio badges now read the DURABLE spec via the
        // derivative-context endpoint (persisted in the derive txn) — invalidate
        // that key so the next read returns real state (no ephemeral stash).
        qc.invalidateQueries({ queryKey: derivativeContextKey(derivative.project_id) });
      }
      qc.invalidateQueries({ queryKey: ['composition', 'work', sourceWork.book_id] });
      onPromoted?.(derivative);
    },
  });

  const canPromote = useMemo(() => draft.name.trim().length > 0, [draft.name]);

  const promote = useCallback(() => {
    if (!token || !canPromote) return;
    promotion.mutate();
  }, [token, canPromote, promotion]);

  return {
    buildDeriveBody,
    promote,
    isPromoting: promotion.isPending,
    error: promotion.isError ? (promotion.error as Error)?.message ?? 'promotion failed' : null,
    canPromote,
  };
}
