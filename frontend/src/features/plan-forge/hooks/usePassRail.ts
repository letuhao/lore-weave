// PlanForge S3 (M4) — the Pass Rail controller. Owns the 7-pass ledger for ONE run: resolve the
// run (an explicit runId from a deep-link, else the book's latest), load its derived pass view,
// poll while a pass job runs, and drive run-pass / checkpoint. No JSX. The poll is the ONE
// synchronization effect (mirrors server job state); run-pass / approve are explicit handlers.
import { useCallback, useEffect, useRef, useState } from 'react';
import { planForgeApi } from '../api';
import type { PlanPassLedger, RunPassBody } from '../types';

const POLL_INTERVAL_MS = 2000;

/** A pass job is active while any pass is running or pending-with-a-job — the poll runs then. */
function isLedgerPolling(ledger: PlanPassLedger | null): boolean {
  if (!ledger) return false;
  return ledger.passes.some((p) => p.status === 'running' || (p.status === 'pending' && !!p.job_id));
}

export interface UsePassRail {
  runId: string | null;
  ledger: PlanPassLedger | null;
  busy: boolean;
  polling: boolean;
  error: string | null;
  /** re-fetch the ledger (also the Lane-B refresh path for an agent write). */
  reload: () => Promise<void>;
  runPass: (passId: string, modelRef?: string, force?: boolean) => Promise<void>;
  reviewCheckpoint: (
    approved: boolean, passId?: string, edits?: Record<string, unknown>,
  ) => Promise<void>;
}

export function usePassRail(
  bookId: string,
  token: string | null,
  explicitRunId?: string | null,
): UsePassRail {
  const [runId, setRunId] = useState<string | null>(explicitRunId ?? null);
  const [ledger, setLedger] = useState<PlanPassLedger | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const genRef = useRef(0);

  const polling = isLedgerPolling(ledger);

  // Resolve the run to show: an explicit deep-link id wins; otherwise the book's most recent run.
  // A book with no runs yet leaves runId null → the panel shows the "compile a plan first" empty state.
  useEffect(() => {
    if (explicitRunId) { setRunId(explicitRunId); return; }
    if (!token) return;
    let cancelled = false;
    void (async () => {
      try {
        const page = await planForgeApi.listRuns(bookId, token, { limit: 1 });
        if (!cancelled) setRunId(page.items[0]?.id ?? null);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => { cancelled = true; };
  }, [bookId, token, explicitRunId]);

  const reload = useCallback(async () => {
    if (!token || !runId) return;
    const gen = ++genRef.current;
    setError(null);
    try {
      const next = await planForgeApi.passStatus(bookId, runId, token);
      if (genRef.current === gen) setLedger(next);
    } catch (e) {
      if (genRef.current === gen) setError((e as Error).message);
    }
  }, [bookId, token, runId]);

  // Load the ledger whenever the resolved run changes.
  useEffect(() => {
    setLedger(null);
    if (runId) void reload();
  }, [runId, reload]);

  // Poll while a pass job is active; stop by derivation when the ledger settles (no timer re-armed).
  useEffect(() => {
    if (!token || !runId || !isLedgerPolling(ledger)) return;
    const gen = genRef.current;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const next = await planForgeApi.passStatus(bookId, runId, token);
        if (!cancelled && genRef.current === gen) setLedger(next);
      } catch (e) {
        if (!cancelled && genRef.current === gen) setError((e as Error).message);
      }
    }, POLL_INTERVAL_MS);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [bookId, token, runId, ledger]);

  const runPass = useCallback(async (passId: string, modelRef?: string, force?: boolean) => {
    if (!token || !runId) return;
    setBusy(true);
    setError(null);
    try {
      const body: RunPassBody = {};
      if (modelRef) body.model_ref = modelRef;
      if (force) body.force = force;
      await planForgeApi.runPass(bookId, runId, passId, body, token);
      await reload(); // pick up the newly-active job so the poll takes over
    } catch (e) {
      // A 409 UPSTREAM_STALE carries {code, pass_id, blockers, message} — surface it, don't swallow.
      setError(extractError(e));
    } finally {
      setBusy(false);
    }
  }, [bookId, token, runId, reload]);

  const reviewCheckpoint = useCallback(async (
    approved: boolean, passId?: string, edits?: Record<string, unknown>,
  ) => {
    if (!token || !runId) return;
    setBusy(true);
    setError(null);
    try {
      const next = await planForgeApi.reviewCheckpoint(
        bookId, runId, { approved, ...(passId ? { pass_id: passId } : {}), ...(edits ? { edits } : {}) }, token,
      );
      setLedger(next);
    } catch (e) {
      // 409 CHECKPOINT_REFUSED (e.g. the cast seed proposal is not yet applied) — surface it.
      setError(extractError(e));
    } finally {
      setBusy(false);
    }
  }, [bookId, token, runId]);

  return { runId, ledger, busy, polling, error, reload, runPass, reviewCheckpoint };
}

/** Pull a human message out of an apiJson error, preferring the server's `detail.message`. */
function extractError(e: unknown): string {
  const err = e as { body?: { detail?: { message?: string; blockers?: string[] } | string }; message?: string };
  const detail = err?.body?.detail;
  if (detail && typeof detail === 'object') {
    const blockers = Array.isArray(detail.blockers) && detail.blockers.length
      ? ` (blocked by: ${detail.blockers.join(', ')})` : '';
    return (detail.message ?? 'request failed') + blockers;
  }
  if (typeof detail === 'string') return detail;
  return (e as Error).message ?? 'request failed';
}
