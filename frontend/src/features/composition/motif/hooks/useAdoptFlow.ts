// W6 §3.2 — the adopt (= clone) Tier-W flow controller. Adopt is a confirm-token
// spend (R2.8): mint a cost estimate → human confirms → POST the token → poll. The
// FE NEVER executes the spend. A quota_exceeded surfaces the non-blocking explainer
// (§4.4), never a silent failure. No JSX.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { isQuotaError, motifApi } from '../api';
import type { CostEstimate, Motif, QuotaError } from '../types';

export type AdoptTarget = { kind: 'user' } | { kind: 'book'; book_id: string; book_name?: string };

/** Pull a QuotaError out of a thrown api error (apiJson attaches the parsed body),
 *  or null if it isn't a quota error. */
function readQuota(err: unknown): QuotaError | null {
  if (!isQuotaError(err)) return null;
  const body = (err as { body?: Partial<QuotaError> }).body;
  if (!body) return null;
  return {
    code: 'quota_exceeded',
    resource: (body.resource as QuotaError['resource']) ?? 'adopt',
    limit: body.limit ?? 0,
    used: body.used ?? 0,
  };
}

export function useAdoptFlow(token: string | null) {
  const qc = useQueryClient();
  const [motifId, setMotifId] = useState<string | null>(null);
  const [target, setTarget] = useState<AdoptTarget>({ kind: 'user' });
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [quota, setQuota] = useState<QuotaError | null>(null);

  // Step 1: open the target picker for a motif (no spend yet).
  const begin = (id: string) => {
    setMotifId(id);
    setTarget({ kind: 'user' });
    setEstimate(null);
    setQuota(null);
  };
  const cancel = () => { setMotifId(null); setEstimate(null); setQuota(null); };

  // Step 2: mint the cost estimate for the chosen target.
  const mint = useMutation({
    mutationFn: () => motifApi.adoptEstimate(motifId!, target, token!),
    onSuccess: (est) => { setEstimate(est); setQuota(null); },
    onError: (err) => { setQuota(readQuota(err)); },
  });

  // Step 3: confirm the minted token → poll → done. Replay-safe (a consumed token
  // resolves as success in the api layer).
  const confirm = useMutation({
    mutationFn: (): Promise<Motif> => motifApi.adoptConfirm(estimate!.confirm_token, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['composition', 'motifs'] });
      cancel();
    },
    onError: (err) => { setQuota(readQuota(err)); },
  });

  return {
    motifId, target, setTarget, estimate, quota,
    begin, cancel, mint, confirm,
    isOpen: motifId != null,
  };
}
