// PlanForge S3 (M4) — the Pass Rail controller. Owns the 7-pass ledger for ONE run: resolve the
// run (an explicit runId from a deep-link, else the book's latest), load its derived pass view,
// poll while a pass job runs, and drive run-pass / checkpoint. No JSX.
//
// The ledger is a REACT-QUERY query (key ['plan-passes', bookId, runId]) — NOT hand-rolled state —
// specifically so the Lane-B `planEffects` handler can refresh the rail after an AGENT write
// (plan_run_pass / plan_review_checkpoint) by invalidating that key. A useState ledger would be
// unreachable from an invalidate (the "invalidateQueries cannot reach hand-rolled state" bug), which
// would make the agent-parity handler a silent no-op.
import { useCallback, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { planForgeApi } from '../api';
import type { PlanPassLedger, RunPassBody } from '../types';

const POLL_INTERVAL_MS = 2000;

function isLedgerPolling(ledger: PlanPassLedger | null | undefined): boolean {
  if (!ledger) return false;
  return ledger.passes.some((p) => p.status === 'running' || (p.status === 'pending' && !!p.job_id));
}

export interface UsePassRail {
  runId: string | null;
  /** H4 — every plan run for this book, so the rail can offer a run picker (not just latest). */
  runs: { id: string; status: string; created_at: string | null }[];
  /** Pin the rail to a specific run (the picker); null re-follows the latest run. */
  setRunId: (runId: string | null) => void;
  ledger: PlanPassLedger | null;
  busy: boolean;
  polling: boolean;
  error: string | null;
  reload: () => Promise<void>;
  runPass: (passId: string, modelRef?: string, force?: boolean) => Promise<void>;
  reviewCheckpoint: (
    approved: boolean, passId?: string, edits?: Record<string, unknown>,
  ) => Promise<void>;
  /** Push the compiled plan into the book's outline tree (§2.6 loop-connect → the manuscript). */
  relink: (target: 'skeleton' | 'scene_plan') => Promise<void>;
  relinkOutput: string | null;
}

export function usePassRail(
  bookId: string,
  token: string | null,
  explicitRunId?: string | null,
): UsePassRail {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [relinkOutput, setRelinkOutput] = useState<string | null>(null);
  // H4 — a manual pick from the run picker; overrides the latest-run default until cleared.
  const [manualRunId, setManualRunId] = useState<string | null>(null);

  // The book's runs (newest first) — the picker's options AND the source of the default (items[0]).
  const runsQ = useQuery({
    queryKey: ['plan-runs-latest', bookId],
    queryFn: () => planForgeApi.listRuns(bookId, token as string, { limit: 50 }),
    enabled: !!token && !explicitRunId,
  });
  const runs = (runsQ.data?.items ?? []).map((r) => ({ id: r.id, status: r.status, created_at: r.created_at }));
  // Resolve the run: an explicit deep-link id wins; else the manual pick; else the most recent run.
  const runId = explicitRunId ?? manualRunId ?? runsQ.data?.items[0]?.id ?? null;
  const latest = runsQ;

  const ledgerQ = useQuery({
    queryKey: ['plan-passes', bookId, runId],
    queryFn: () => planForgeApi.passStatus(bookId, runId as string, token as string),
    enabled: !!token && !!runId,
    // Poll only while a pass job is active; stop by derivation when the ledger settles.
    refetchInterval: (q) => (isLedgerPolling(q.state.data as PlanPassLedger | undefined) ? POLL_INTERVAL_MS : false),
  });

  const ledger = ledgerQ.data ?? null;
  const polling = isLedgerPolling(ledger);
  const error =
    actionError ??
    (ledgerQ.error ? (ledgerQ.error as Error).message : null) ??
    (latest.error ? (latest.error as Error).message : null);

  const invalidate = useCallback(
    () => qc.invalidateQueries({ queryKey: ['plan-passes', bookId, runId] }),
    [qc, bookId, runId],
  );

  const reload = useCallback(async () => { await invalidate(); }, [invalidate]);

  const runPass = useCallback(async (passId: string, modelRef?: string, force?: boolean) => {
    if (!token || !runId) return;
    setBusy(true); setActionError(null);
    try {
      const body: RunPassBody = {};
      if (modelRef) body.model_ref = modelRef;
      if (force) body.force = force;
      await planForgeApi.runPass(bookId, runId, passId, body, token);
      await invalidate(); // pick up the newly-active job so the poll takes over
    } catch (e) {
      setActionError(extractError(e)); // 409 UPSTREAM_STALE carries blockers — surface, don't swallow
    } finally {
      setBusy(false);
    }
  }, [bookId, token, runId, invalidate]);

  const reviewCheckpoint = useCallback(async (
    approved: boolean, passId?: string, edits?: Record<string, unknown>,
  ) => {
    if (!token || !runId) return;
    setBusy(true); setActionError(null);
    try {
      const next = await planForgeApi.reviewCheckpoint(
        bookId, runId,
        { approved, ...(passId ? { pass_id: passId } : {}), ...(edits ? { edits } : {}) }, token,
      );
      qc.setQueryData(['plan-passes', bookId, runId], next);
    } catch (e) {
      setActionError(extractError(e)); // 409 CHECKPOINT_REFUSED (seed not applied) — surface it
    } finally {
      setBusy(false);
    }
  }, [bookId, token, runId, qc]);

  const relink = useCallback(async (target: 'skeleton' | 'scene_plan') => {
    if (!token || !runId) return;
    setBusy(true); setActionError(null); setRelinkOutput(null);
    try {
      await planForgeApi.relink(bookId, runId, target, token);
      setRelinkOutput(target === 'skeleton'
        ? 'Linked arcs + chapters into the outline.'
        : 'Linked the scenes into the outline.');
    } catch (e) {
      // 409 LINK_REFUSED (e.g. nothing compiled / no scene plan yet) — surface it.
      setActionError(extractError(e));
    } finally {
      setBusy(false);
    }
  }, [bookId, token, runId]);

  return {
    runId, runs, setRunId: setManualRunId, ledger, busy, polling, error, reload,
    runPass, reviewCheckpoint, relink, relinkOutput,
  };
}

/** Pull a human message out of an apiJson error, preferring the server's `detail.message`. */
function extractError(e: unknown): string {
  const err = e as { body?: { detail?: { message?: string; blockers?: string[] } | string } } & Error;
  const detail = err?.body?.detail;
  if (detail && typeof detail === 'object') {
    const blockers = Array.isArray(detail.blockers) && detail.blockers.length
      ? ` (blocked by: ${detail.blockers.join(', ')})` : '';
    return (detail.message ?? 'request failed') + blockers;
  }
  if (typeof detail === 'string') return detail;
  return (e as Error).message ?? 'request failed';
}
