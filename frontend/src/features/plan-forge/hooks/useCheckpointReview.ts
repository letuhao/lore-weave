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
  //
  // 🔴 #265 — `!proposalId` was doing double duty. It is meant to say "advisory pass, no gate",
  // but it is ALSO true for a BLOCKING pass whose proposal was never opened, and in that state the
  // button was enabled while the server refused forever:
  //
  //   409 CHECKPOINT_REFUSED — "cast cannot be accepted before its glossary seed proposal exists"
  //
  // which is exactly what this file's own header warns about ("409s the approve forever"). That
  // happens for real: a cast pass that produced nothing writes `{"cast": []}`, the job opens no
  // proposal by design ("you cannot accept a cast that does not exist"), and the author is left
  // with an enabled button that can never work and no reason given.
  //
  // Blocking passes are now gated on the proposal EXISTING as well as being applied. The refusal
  // is the server's, and the UI should not offer an action it knows will be refused.
  const blocking = pass?.checkpoint === 'blocking';
  const canApprove = blocking
    ? proposal?.status === 'applied'
    : (!proposalId || proposal?.status === 'applied');

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
