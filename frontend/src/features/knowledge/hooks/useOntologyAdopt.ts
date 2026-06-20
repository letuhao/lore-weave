import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { ontologyApi } from '../api/ontology';
import type {
  AdoptPayload,
  GraphSchemaSummary,
  NeedsGlossary,
} from '../types/ontology';

// ─────────────────────────────────────────────────────────────────────────────
// useOntologyAdopt — controller for the project adopt (copy-down) flow.
//
// M1 adopt-gate: the BE 422s with a NeedsGlossary body when the project's
// glossary is missing a `required` node-kind. The shared apiJson throws an Error
// carrying `.status` + `.body` (no second round-trip). We DERIVE `needsGlossary`
// from `mutation.error` (no setState-in-onError — keeping onError side-effect
// free matches the house mutation hooks and avoids an extra render that races
// React Query's internal rejected-promise settling). The AdoptPicker renders the
// blocker list + a deep-link to glossary off `needsGlossary`. After the user
// fixes the gap and returns, re-running adopt is idempotent (BE re-checks);
// `clearGate` dismisses the surfaced gate (until the next adopt attempt).
//
// `acknowledge_optional_gaps` lets the caller proceed past missing *optional*
// kinds — those never 422; the BE warns + parks runtime mismatches to triage.
// ─────────────────────────────────────────────────────────────────────────────

interface AdoptError extends Error {
  status?: number;
  code?: string;
  body?: unknown;
}

function asNeedsGlossary(err: AdoptError | null): NeedsGlossary | null {
  if (!err || err.status !== 422) return null;
  const body = err.body;
  if (
    typeof body === 'object' &&
    body !== null &&
    'needs_glossary' in body &&
    typeof (body as NeedsGlossary).needs_glossary === 'object'
  ) {
    return body as NeedsGlossary;
  }
  return null;
}

export function useOntologyAdopt(projectId: string) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  // A user-dismissed gate is suppressed until the next adopt attempt resets it.
  const [dismissed, setDismissed] = useState(false);

  const mutation = useMutation<GraphSchemaSummary, AdoptError, AdoptPayload>({
    mutationFn: (payload) => ontologyApi.adopt(projectId, payload, accessToken!),
    onMutate: () => {
      // A fresh attempt un-dismisses any prior gate.
      setDismissed(false);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kg-graph-schemas'] });
      queryClient.invalidateQueries({
        queryKey: ['kg-resolved-schema', projectId],
      });
    },
  });

  // adopt is `mutation.mutateAsync` exposed DIRECTLY (the house convention — see
  // useEntityMutations.update). It REJECTS on failure (incl. the M1 422); the
  // gate is surfaced as derived `needsGlossary` state, so the AdoptPicker page
  // awaits adopt inside a try/catch and branches on `needsGlossary` — the
  // rejection never escapes. Callers pass the payload object
  // (`{ source_schema_id, acknowledge_optional_gaps }`).
  const adopt = mutation.mutateAsync;

  const clearGate = () => setDismissed(true);

  // Gate derived from the last error (cleared on dismiss / next attempt).
  const needsGlossary = dismissed ? null : asNeedsGlossary(mutation.error ?? null);

  return {
    adopt,
    clearGate,
    needsGlossary,
    isAdopting: mutation.isPending,
    // A 422 gate is NOT a generic error — only a non-gate failure surfaces here.
    isError: mutation.isError && !needsGlossary,
    error: mutation.error,
    adopted: mutation.data ?? null,
  };
}
