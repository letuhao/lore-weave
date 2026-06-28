// D-W10-ARC-CONFORMANCE-DEEP-FE — the DEEP arc-conformance Tier-W flow controller.
// The deep overlay re-tags the book's prose (~120 LLM calls), so it runs as a
// 202+poll JOB: PROPOSE (mint a confirm token via the FE→MCP-tool bridge) → human
// confirms the cost → poll the job → the deep arc report. The FE never executes the
// spend itself. No JSX — the panel owns presentation.
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { motifApi } from '../api';
import type { ArcConformance, CostEstimate } from '../types';

export function useArcConformanceRun(
  projectId: string | null | undefined,
  arcTemplateId: string | null | undefined,
  token: string | null,
) {
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [result, setResult] = useState<ArcConformance | null>(null);

  // Step 1 — mint the cost estimate + confirm token for the chosen model (no spend).
  const mint = useMutation({
    mutationFn: (modelRef: string) =>
      motifApi.arcConformanceRunPropose(
        { projectId: projectId!, arcTemplateId: arcTemplateId!, modelRef },
        token!,
      ),
    onSuccess: setEstimate,
  });

  // Step 2 — confirm the token → poll the job → the deep arc report.
  const confirm = useMutation({
    mutationFn: () => motifApi.arcConformanceRunConfirm(estimate!.confirm_token, token!),
    onSuccess: (r) => {
      setResult(r);
      setEstimate(null);
    },
  });

  // Cancel the pending estimate (before confirm); keep any prior result on screen.
  const cancel = () => setEstimate(null);
  // Fully reset (e.g. to re-run with a different model).
  const reset = () => {
    setEstimate(null);
    setResult(null);
    mint.reset();
    confirm.reset();
  };

  return { estimate, result, mint, confirm, cancel, reset };
}
