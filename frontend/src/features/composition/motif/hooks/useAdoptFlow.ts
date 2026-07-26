// W6 §3.2 — the adopt (= clone) Tier-W flow controller. Adopt clones a public/system
// motif into YOUR library via a confirm-token spend (R2.8): PROPOSE a confirm token
// (FE→MCP-tool bridge) → human confirms → the JWT-authed confirm clones it. The FE
// NEVER executes the spend. Adopt defaults to the user's GLOBAL tier; when a bookId is
// in context the caller may instead target='book' to LABEL the clone for that book
// (D-MOTIF-ADOPT-PER-BOOK = model A book-scoped filter). A quota ceiling surfaces the
// §4.4 non-blocking explainer. No JSX.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { isQuotaError, motifApi } from '../api';
import type { CostEstimate, Motif, QuotaError } from '../types';

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

export function useAdoptFlow(token: string | null, bookId?: string | null) {
  const qc = useQueryClient();
  const [motifId, setMotifId] = useState<string | null>(null);
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [quota, setQuota] = useState<QuotaError | null>(null);
  // The adopt destination — the user's global library, or (when a bookId is in context) this
  // book's PRIVATE label (D-MOTIF-ADOPT-PER-BOOK, model A) or its SHARED tier (model B,
  // D-MOTIF-ADOPT-BOOK-COLLAB-TIER — visible to collaborators). Chosen BEFORE mint (the target
  // is baked into the minted confirm token). Resets to 'user' on each begin().
  const [target, setTarget] = useState<'user' | 'book' | 'book_shared'>('user');
  const canTargetBook = !!bookId;

  // Step 1: open the adopt confirm for a motif (no spend yet).
  const begin = (id: string) => {
    setMotifId(id);
    setEstimate(null);
    setQuota(null);
    setTarget('user');
  };
  const cancel = () => { setMotifId(null); setEstimate(null); setQuota(null); setTarget('user'); };

  // Step 2: mint the confirm token (the propose; no $ — adopt is quota-gated). 'book' labels a
  // private per-user copy; 'book_shared' adopts into the book's shared tier; 'user' (or no
  // bookId) stays global.
  const mint = useMutation({
    mutationFn: () => motifApi.adoptEstimate(
      motifId!, token!,
      (target === 'book' || target === 'book_shared') && bookId
        ? { bookId, shared: target === 'book_shared' }
        : undefined,
    ),
    onSuccess: (est) => { setEstimate(est); setQuota(null); },
    onError: (err) => { setQuota(readQuota(err)); },
  });

  // Step 3: confirm the minted token → the clone is created synchronously.
  const confirm = useMutation({
    mutationFn: (): Promise<Motif> => motifApi.adoptConfirm(estimate!.confirm_token, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['composition', 'motifs'] });
      cancel();
    },
    onError: (err) => { setQuota(readQuota(err)); },
  });

  return {
    motifId, estimate, quota,
    target, setTarget, canTargetBook,
    begin, cancel, mint, confirm,
    isOpen: motifId != null,
  };
}
