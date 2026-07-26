import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { ontologyApi } from '../api/ontology';
import type {
  AdoptPayload,
  AdoptPreview,
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

export function useOntologyAdopt(
  projectId: string,
  selectedSchemaId?: string | null,
) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  // A user-dismissed gate is suppressed until the next adopt attempt resets it.
  const [dismissed, setDismissed] = useState(false);
  // The user must explicitly acknowledge the loss warning before adopt re-enables.
  // Keyed to the schema id that was acknowledged (NOT a bare boolean) so selecting
  // a DIFFERENT template auto-re-arms the gate without a useEffect reset — the ack
  // simply no longer matches the new candidate (house rule: no useEffect for
  // reacting to a prop change).
  const [ackedSchemaId, setAckedSchemaId] = useState<string | null>(null);

  // D-KG-LC-REVADOPT-LOSS: auto-fetch the "what you'll lose" preview whenever a
  // template is selected. Re-adopt replaces the project's active schema and
  // silently drops customizations the template lacks — the picker warns + gates
  // the destructive button on this. Read-only; refetch is unnecessary (the source
  // tree only changes via sync, a separate flow). A fresh selection un-acks the
  // prior warning so the gate re-arms per candidate.
  const preview = useQuery<AdoptPreview>({
    queryKey: ['kg-adopt-preview', projectId, selectedSchemaId],
    queryFn: () =>
      ontologyApi.adoptPreview(
        projectId,
        { source_schema_id: selectedSchemaId! },
        accessToken!,
      ),
    enabled: !!selectedSchemaId && !!accessToken,
    staleTime: Infinity,
  });

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

  // Loss warning derived from the preview: it fires when the project has a
  // current schema AND the candidate would drop/overwrite customizations. The
  // user clears it via `acknowledgeLoss`, which records the candidate id; the
  // warning is suppressed only while the acked id matches the current selection.
  const wouldLose = preview.data?.would_lose ?? [];
  const hasLoss = !!preview.data?.has_current && wouldLose.length > 0;
  const lossAcknowledged = !!selectedSchemaId && ackedSchemaId === selectedSchemaId;
  const lossBlocked = hasLoss && !lossAcknowledged;

  const acknowledgeLoss = () => setAckedSchemaId(selectedSchemaId ?? null);

  return {
    adopt,
    clearGate,
    needsGlossary,
    isAdopting: mutation.isPending,
    // A 422 gate is NOT a generic error — only a non-gate failure surfaces here.
    isError: mutation.isError && !needsGlossary,
    error: mutation.error,
    adopted: mutation.data ?? null,
    // ── re-adopt loss preview (D-KG-LC-REVADOPT-LOSS) ──
    wouldLose,
    hasLoss,
    /** true while the destructive adopt must stay disabled (loss un-acknowledged) */
    lossBlocked,
    isPreviewLoading: preview.isLoading && !!selectedSchemaId,
    acknowledgeLoss,
  };
}
