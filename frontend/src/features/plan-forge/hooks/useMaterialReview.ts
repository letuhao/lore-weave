// Controller for the material keep-or-drop step (MVC: this owns the state, MaterialReview renders).
//
// The step sits in the PROPOSE/SPEC phase, not in the pass rail: it improves the spec that `compile`
// reads, whereas every pass reads the package `compile` produces. Putting it in the rail would run
// it after compile and lose the entire point.
import { useCallback, useEffect, useState } from 'react';
import { planForgeApi } from '../api';
import type { KeepMaterialResult, MaterialPacket } from '../types';

export interface MaterialReviewState {
  packet: MaterialPacket | null;
  busy: boolean;
  error: string | null;
  result: KeepMaterialResult | null;
  /** Per-kind, the quotes the author has NOT dropped. Absent kind = untouched (all still kept). */
  kept: Record<string, string[]>;
  find: (modelRef?: string) => Promise<void>;
  setKept: (kind: string, quotes: string[]) => void;
  keep: () => Promise<void>;
  reset: () => void;
}

export function useMaterialReview(
  bookId: string | null, runId: string | null, token: string | null,
): MaterialReviewState {
  const [packet, setPacket] = useState<MaterialPacket | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<KeepMaterialResult | null>(null);
  const [kept, setKeptState] = useState<Record<string, string[]>>({});

  // Load the LAST packet on mount — a synchronisation with server state, which is what useEffect is
  // for (the repo rule bans it for reacting to user actions, not for this). Free: the GET never
  // searches. Without it, closing the panel threw away a result the author had already paid for.
  useEffect(() => {
    if (!bookId || !runId || !token) return;
    let live = true;
    void planForgeApi.getMissingMaterial(bookId, runId, token)
      .then((p) => {
        if (!live || !p) return;
        setPacket(p);
        setKeptState(Object.fromEntries(
          (p.review ?? []).map((r) => [r.kind, r.candidates.map((c) => c.quote)])));
      })
      .catch(() => { /* a missing prior packet is not an error worth showing */ });
    return () => { live = false; };
  }, [bookId, runId, token]);

  const find = useCallback(async (modelRef?: string) => {
    if (!bookId || !runId || !token) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const p = await planForgeApi.findMissingMaterial(bookId, runId, token, modelRef);
      setPacket(p);
      // Default = everything found is kept. Dropping is the deliberate act, which matches the
      // editor this renders through: you remove the rows you do not want.
      setKeptState(Object.fromEntries(p.review.map((r) => [r.kind, r.candidates.map((c) => c.quote)])));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [bookId, runId, token]);

  const setKept = useCallback((kind: string, quotes: string[]) => {
    setKeptState((k) => ({ ...k, [kind]: quotes }));
  }, []);

  const keep = useCallback(async () => {
    if (!bookId || !runId || !token) return;
    setBusy(true); setError(null);
    try {
      setResult(await planForgeApi.keepMaterial(bookId, runId, kept, token));
      // The packet is now stale against the spec it just changed — clearing it stops the author
      // acting twice on the same candidates, and the next `find` re-reads the board.
      setPacket(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [bookId, runId, token, kept]);

  const reset = useCallback(() => {
    setPacket(null); setError(null); setResult(null); setKeptState({});
  }, []);

  return { packet, busy, error, result, kept, find, setKept, keep, reset };
}
