// LOOM Composition · M6 Polish (controller) — owns the self-heal review-gate state.
//
// Runs the cheap-stack PROPOSE pass for the open chapter, holds the proposals + the
// per-edit acceptance set (deterministic pre-checked, semantic unchecked = do-no-harm),
// and derives the healed text from the accepted subset (the JS mirror of the engine's
// apply, so the preview byte-matches the backend). The component only renders + calls back.
import { useCallback, useMemo, useState } from 'react';

import {
  applySelfHealEdits,
  compositionApi,
  type SelfHealProposal,
  type SelfHealProposalResponse,
} from '../api';

export interface PolishOptions {
  verify?: boolean;
  verifyK?: number;
  voteK?: number;
  prefilter?: boolean;
}

export function usePolishProposals(
  projectId: string | null,
  chapterId: string | null,
  token: string | null,
  modelRef: string,
) {
  const [proposals, setProposals] = useState<SelfHealProposal[]>([]);
  const [sourceText, setSourceText] = useState('');
  const [draftVersion, setDraftVersion] = useState<number | null>(null);
  const [stats, setStats] = useState<SelfHealProposalResponse['stats']>();
  const [acceptedIds, setAcceptedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ran, setRan] = useState(false);

  const run = useCallback(
    async (opts?: PolishOptions) => {
      if (!projectId || !chapterId || !token || !modelRef) return;
      setLoading(true);
      setError(null);
      try {
        const r = await compositionApi.proposeSelfHeal(
          projectId,
          { chapterId, modelRef, ...opts },
          token,
        );
        const props = r.proposals ?? [];
        setProposals(props);
        setSourceText(r.source_text ?? '');
        setDraftVersion(r.draft_version ?? null);
        setStats(r.stats);
        // pre-check the edits the backend recommends — deterministic always, plus the semantic
        // edits the comparative re-ranker approved (falls back to tier when `recommended` absent).
        setAcceptedIds(new Set(
          props.filter((p) => p.recommended ?? p.tier === 'deterministic').map((p) => p.id)));
        setRan(true);
      } catch (e) {
        setError((e as Error).message || 'Polish failed');
      } finally {
        setLoading(false);
      }
    },
    [projectId, chapterId, token, modelRef],
  );

  const toggle = useCallback((id: string) => {
    setAcceptedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // bulk accept/clear, optionally scoped to a tier ("accept all deterministic")
  const bulk = useCallback(
    (on: boolean, tier?: 'deterministic' | 'semantic') => {
      setAcceptedIds((prev) => {
        const next = new Set(prev);
        for (const p of proposals) {
          if (tier && p.tier !== tier) continue;
          if (on) next.add(p.id);
          else next.delete(p.id);
        }
        return next;
      });
    },
    [proposals],
  );

  const healedText = useMemo(
    () => applySelfHealEdits(sourceText, proposals, acceptedIds),
    [sourceText, proposals, acceptedIds],
  );

  return {
    proposals,
    sourceText,
    draftVersion,
    stats,
    acceptedIds,
    loading,
    error,
    ran,
    run,
    toggle,
    bulk,
    healedText,
  };
}
