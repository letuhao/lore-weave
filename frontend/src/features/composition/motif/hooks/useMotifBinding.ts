// W6 §3.2 / §4.6 — the planner-binding controller CONSUMED BY W2's PlannerView (the
// one documented seam, MD-1: W6 ships this hook + the MotifBinding* children; W2
// imports + renders them — W6 never edits PlannerView.tsx). Owns: swap / rebindRole /
// clearMotif / chainIt / regenerateScene, all invalidating the decompose-preview
// query so the tree re-renders (NO useEffect for event handling). A failed swap
// keeps the prior binding (no destructive optimism). No JSX.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiJson } from '@/api';
import type { CommitAndGenerateRoute, SuccessionHint } from '../types';

const BASE = '/v1/composition';

export type UseMotifBindingArgs = {
  projectId: string;
  bookId: string;
  nodeId: string;
  token: string | null;
};

export function useMotifBinding({ projectId, bookId, nodeId, token }: UseMotifBindingArgs) {
  const qc = useQueryClient();
  // Invalidate W2's decompose-preview query so the planner tree re-renders with the
  // new binding. The key prefix matches W2's preview cache (project-scoped).
  const invalidatePreview = () =>
    qc.invalidateQueries({ queryKey: ['composition', 'decompose', projectId] });

  // swap → PATCH …/outline/{node}/motif (archive-not-delete per R2.6). A failure
  // does NOT mutate local state (the mutation rejects; the caller keeps the prior
  // binding + toasts) — react-query's onError path leaves the cache untouched until
  // a successful invalidate.
  const swap = useMutation({
    mutationFn: (motifId: string) =>
      apiJson(`${BASE}/works/${projectId}/outline/${nodeId}/motif`, {
        method: 'PATCH', body: JSON.stringify({ motif_id: motifId, book_id: bookId }), token: token!,
      }),
    onSuccess: invalidatePreview,
  });

  const rebindRole = useMutation({
    mutationFn: (v: { roleKey: string; entityId: string | null }) =>
      apiJson(`${BASE}/works/${projectId}/outline/${nodeId}/motif/role`, {
        method: 'PATCH', body: JSON.stringify({ role_key: v.roleKey, entity_id: v.entityId }), token: token!,
      }),
    onSuccess: invalidatePreview,
  });

  // clearMotif → free-form fallback (A3 invent). Archive-not-delete: the binding is
  // removed but the application ledger row survives (history).
  const clearMotif = useMutation({
    mutationFn: () =>
      apiJson(`${BASE}/works/${projectId}/outline/${nodeId}/motif`, { method: 'DELETE', token: token! }),
    onSuccess: invalidatePreview,
  });

  // chainIt → pre-seed the next chapter with the legal-succession motif.
  const chainIt = useMutation({
    mutationFn: (hint: SuccessionHint) =>
      apiJson(`${BASE}/works/${projectId}/outline/${hint.for_node_id}/motif/chain`, {
        method: 'POST', body: JSON.stringify({ to_motif_code: hint.to_motif_code }), token: token!,
      }),
    onSuccess: invalidatePreview,
  });

  const regenerateScene = useMutation({
    mutationFn: (sceneId: string) =>
      apiJson(`${BASE}/works/${projectId}/scenes/${sceneId}/regenerate-to-beat`, { method: 'POST', token: token! }),
    onSuccess: invalidatePreview,
  });

  // §4.6 — the bind → COMMIT → GENERATE contract. W6 returns WHERE to go; W2 wires
  // it to the panel's selectTab('compose'|'assemble') + setSceneId (the seam). This
  // closes the H-8 dead-end: bind → generate → verify is ONE path, not three islands.
  const commitAndGenerate = (sceneId: string): CommitAndGenerateRoute => ({ tab: 'compose', sceneId });

  return { swap, rebindRole, clearMotif, chainIt, regenerateScene, commitAndGenerate };
}
