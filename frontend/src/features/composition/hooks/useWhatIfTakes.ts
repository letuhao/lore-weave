// LOOM Composition (WS-B3 M2) — what-if take generation + judge orchestration.
//
// Per the decided M2 contract (spec §2b): a "take" is an alternate of the ANCHOR scene,
// generated via the existing auto (diverge→converge) path on the CANON project
// (pre-promote, non-persisting), then judged by the existing critic (its dims, not yet
// a vs-canon delta). Kept out of SceneGraphCanvas so that component stays a view and
// this wiring is unit-testable. Writes results back through `useSceneWhatIf.updateAlt`.
import { useCallback } from 'react';
import { useAutoGenerate, useCorrection } from './useAutoGenerate';
import { useCritique } from './useCritique';
import type { WhatIfAlt } from './useSceneWhatIf';

export function useWhatIfTakes(opts: {
  projectId: string;
  token: string | null;
  updateAlt: (id: string, patch: Partial<WhatIfAlt>) => void;
}) {
  const auto = useAutoGenerate(opts.token);
  const { critique } = useCritique(opts.token);
  // Touch useCorrection so the auto-path import stays consistent with the co-writer
  // (no correction is captured for an ephemeral take — it isn't an authored choice yet).
  useCorrection(opts.token);

  const generateTake = useCallback(
    (altId: string, anchorSceneId: string, model: { modelRef: string; modelKind?: string; modelName?: string }) => {
      if (!model.modelRef) return;
      opts.updateAlt(altId, { status: 'generating', take: undefined });
      auto.mutate(
        {
          projectId: opts.projectId,
          outlineNodeId: anchorSceneId,
          // The auto path IS diverge→converge (its K candidates ARE the variation), so
          // the operation should be the real 'draft_scene' (the proper beat/goal/POV/
          // synopsis brief). A made-up 'diverge' is unrecognised by the drafter and
          // falls back to a WEAKER generic instruction (/review-impl MED).
          operation: 'draft_scene',
          modelSource: 'user_model',
          modelRef: model.modelRef,
          modelKind: model.modelKind,
          modelName: model.modelName,
        },
        {
          onSuccess: (data) => {
            // ghost first (so the writer can read it immediately), judge async after.
            opts.updateAlt(altId, { status: 'ready', take: { ghost: data.text, jobId: data.job_id, judge: null } });
            critique.mutate(
              { jobId: data.job_id, passage: data.text },
              { onSuccess: (j) => opts.updateAlt(altId, { take: { ghost: data.text, jobId: data.job_id, judge: j.critic } }) },
            );
          },
          onError: () => opts.updateAlt(altId, { status: 'error' }),
        },
      );
    },
    [auto, critique, opts],
  );

  return { generateTake, generating: auto.isPending };
}
