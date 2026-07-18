// PlanForge S3 (M4-CP) — the blocking-checkpoint review controller. Loads the pass artifact's
// CONTENT (so the human can read what they're approving) and, for `cast`, the glossary SEED
// proposal it is gated on (PF-7): `cast` cannot be accepted until that proposal is `applied`, so
// the review must be able to fetch it (BE-20 surfaces its id) and apply it. No JSX.
import { useCallback, useEffect, useRef, useState } from 'react';
import { planForgeApi } from '../api';
import type { BootstrapProposal, PlanArtifactDetail, PlanPass } from '../types';

export interface UseCheckpointReview {
  artifact: PlanArtifactDetail | null;
  proposal: BootstrapProposal | null; // only for cast (a pass with a bootstrap_proposal_id)
  loading: boolean;
  busy: boolean;
  error: string | null;
  /** true once the seed gate is satisfied (advisory passes have no gate → always true). */
  canApprove: boolean;
  /** approve/apply the glossary seed so `cast` becomes acceptable (PF-7). */
  applySeed: () => Promise<void>;
}

export function useCheckpointReview(
  bookId: string, runId: string | null, pass: PlanPass | null, token: string | null,
): UseCheckpointReview {
  const [artifact, setArtifact] = useState<PlanArtifactDetail | null>(null);
  const [proposal, setProposal] = useState<BootstrapProposal | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const genRef = useRef(0);

  const proposalId = pass?.bootstrap_proposal_id ?? null;

  // Load the artifact content + (for cast) the seed proposal whenever the reviewed pass changes.
  useEffect(() => {
    if (!token || !runId || !pass) { setArtifact(null); setProposal(null); return; }
    const gen = ++genRef.current;
    setLoading(true); setError(null); setArtifact(null); setProposal(null);
    void (async () => {
      try {
        if (pass.artifact_id) {
          const art = await planForgeApi.getArtifact(bookId, runId, pass.artifact_id, token);
          if (genRef.current === gen) setArtifact(art);
        }
        if (proposalId) {
          // A missing/foreign proposal is not fatal — the gate copy still renders; don't hard-fail.
          try {
            const p = await planForgeApi.bootstrapGet(bookId, proposalId, token);
            if (genRef.current === gen) setProposal(p);
          } catch { /* leave proposal null → the gate shows "seed unavailable" */ }
        }
      } catch (e) {
        if (genRef.current === gen) setError((e as Error).message);
      } finally {
        if (genRef.current === gen) setLoading(false);
      }
    })();
  }, [bookId, runId, token, pass, proposalId]);

  // A non-cast (advisory) pass has no seed gate. Cast is gated until its proposal is `applied`.
  const canApprove = !proposalId || proposal?.status === 'applied';

  const applySeed = useCallback(async () => {
    if (!token || !proposalId) return;
    setBusy(true); setError(null);
    try {
      // pending → approve → apply; approved → apply. Idempotent enough for a retry.
      let p = proposal ?? await planForgeApi.bootstrapGet(bookId, proposalId, token);
      if (p.status === 'pending') p = await planForgeApi.bootstrapApprove(bookId, proposalId, token);
      if (p.status === 'approved' || p.status === 'applying') {
        p = await planForgeApi.bootstrapApply(bookId, proposalId, token);
      }
      setProposal(p);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [bookId, token, proposalId, proposal]);

  return { artifact, proposal, loading, busy, error, canApprove, applySeed };
}
