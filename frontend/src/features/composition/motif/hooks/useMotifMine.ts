// WI-1 (D-MOTIF-MINE-FE-BRIDGE) — the corpus-mining Tier-W flow controller. Mining
// spends LLM tokens (PrefixSpan over your :Event corpus → LLM abstraction → judge), so
// it runs as a 202+poll JOB: PROPOSE (mint a confirm token + $ estimate via the FE→MCP
// bridge) → human confirms the cost → poll → the mined drafts. The FE never executes the
// spend. No JSX — MotifMinePanel owns presentation. Mirrors useArcConformanceRun.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { motifApi, isQuotaError } from '../api';
import type { CostEstimate, MineResult } from '../types';

export type MineScope = 'book' | 'corpus';

export function useMotifMine(token: string | null, bookId?: string | null) {
  const qc = useQueryClient();
  // run-config — book scope needs a bookId; without one only corpus is offered.
  const [scope, setScope] = useState<MineScope>(bookId ? 'book' : 'corpus');
  const [minSupport, setMinSupport] = useState(3);
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [result, setResult] = useState<MineResult | null>(null);

  // Step 1 — mint the cost estimate + confirm token for the chosen model (no spend).
  const mint = useMutation({
    mutationFn: (modelRef: string) =>
      motifApi.minePropose(
        { scope, bookId, minSupport, modelRef },
        token!,
      ),
    onSuccess: setEstimate,
  });

  // Step 2 — confirm the token → poll the mine job → the MineResult; refresh the
  // Drafts tab so the newly-mined drafts appear.
  const confirm = useMutation({
    mutationFn: () => motifApi.mineConfirm(estimate!.confirm_token, token!),
    onSuccess: (r) => {
      setResult(r);
      setEstimate(null);
      qc.invalidateQueries({ queryKey: ['composition', 'motifs'] });
    },
  });

  const cancel = () => setEstimate(null);
  const reset = () => {
    setEstimate(null);
    setResult(null);
    mint.reset();
    confirm.reset();
  };

  const error = (mint.error || confirm.error) as unknown;
  return {
    scope, setScope, minSupport, setMinSupport,
    canBook: !!bookId,
    estimate, result,
    mint, confirm, cancel, reset,
    isQuota: isQuotaError(error),
    error,
  };
}
