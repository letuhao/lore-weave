// 24 PH21 — the empty state's "Extract the plan from the manuscript" CTA (the 22 SC6 DECOMPILER).
//
// One EDIT-gated POST. Deterministic and $0 (no LLM), which is why it is a direct call and not a
// propose→confirm priced card — the priced half of the decompiler is the arc-grouping LLM step, and
// that stays an MCP tool (agentic logic goes through the agent, MCP-first invariant).
//
// On success the whole Hub must re-read: the extraction mints chapter + scene nodes and (because
// arc grouping has not run) they are all UNASSIGNED. So we invalidate the react-query surfaces AND
// call reloadWindows() — the window slices are hand-rolled state that `invalidateQueries` cannot
// reach, which is the exact bug H5 shipped once (`invalidatequeries-cannot-reach-hand-rolled-state`).
import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { materializeScenes, type MaterializeScenesResult } from '../api';

export interface ExtractPlanResult {
  run: () => void;
  extracting: boolean;
  result: MaterializeScenesResult | null;
  error: string | null;
}

export function useExtractPlan(
  bookId: string,
  token: string | null,
  reloadWindows: () => void,
): ExtractPlanResult {
  const qc = useQueryClient();
  const [extracting, setExtracting] = useState(false);
  const [result, setResult] = useState<MaterializeScenesResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(() => {
    if (!token || !bookId || extracting) return;
    setExtracting(true);
    setError(null);
    setResult(null);
    void (async () => {
      try {
        const res = await materializeScenes(bookId, token);
        setResult(res);
        // The graceful no-Work guard: the server reports it rather than 500ing, so we must SURFACE
        // it. A 200 whose `work_resolved` is false did no work — reporting "extracted!" over that
        // would be the silent-success bug.
        if (!res.work_resolved && res.scenes_total > 0) {
          setError(
            res.detail ??
              'The plan could not be attached to this book (no Work resolved). Nothing was extracted.',
          );
          return;
        }
        await qc.invalidateQueries({ queryKey: ['plan-hub'] });
        reloadWindows();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Extraction failed');
      } finally {
        setExtracting(false);
      }
    })();
  }, [bookId, token, extracting, qc, reloadWindows]);

  return { run, extracting, result, error };
}
