// World Setup controller — owns ALL pipeline logic + state; the panel only renders.
// (Frontend MVC: hooks are controllers, components are views.)
import { useCallback, useEffect, useRef, useState } from 'react';

import { worldSetupApi } from '../api';
import type { BuildEdge, BuildRun, WorklistItem } from '../types';

/** Statuses where the server is still working — the only ones worth polling. */
const IN_FLIGHT = new Set(['planning', 'building', 'proposing', 'kg_projecting']);
const POLL_MS = 4000;

/** The statuses that hold `uq_glossary_build_active_book` — i.e. the ones that answer
 *  ACTIVE_RUN to a new run. Mirrors the index, and DELIBERATELY wider than `IN_FLIGHT`:
 *  `edges_ready` is a human checkpoint where nothing is running, and it still blocks. */
const BLOCKING = new Set([
  'planning', 'plan_ready', 'building', 'proposing', 'kg_projecting', 'edges_ready',
]);

export interface UseWorldSetup {
  run: BuildRun | null;
  busy: boolean;
  error: string | null;
  start: (sourceText: string, modelRef: string, lang: string) => Promise<void>;
  approvePlan: (worklist: WorklistItem[]) => Promise<void>;
  projectKg: () => Promise<void>;
  approveEdges: (edges: BuildEdge[]) => Promise<void>;
  cancel: () => Promise<void>;
  reset: () => void;
  /** The run that is holding this book's single active slot, when `start` was refused.
   *
   * The server enforces one in-flight run per book and answers ACTIVE_RUN. Until now the
   * panel printed that code and stopped — no resume, no cancel, no run id. A book whose run
   * had been abandoned at a review checkpoint could not be worked on again from the UI at
   * all, and the API's own `/cancel` refused the two states that hold the slot. Found on a
   * real book: a run sat at `edges_ready` for a week. */
  blockedBy: BuildRun | null;
  /** Adopt the blocking run — the wizard jumps to whatever checkpoint it is waiting at. */
  adoptBlocking: () => void;
  /** Cancel the blocking run so a fresh one can start. */
  cancelBlocking: () => Promise<void>;
}

function message(e: unknown): string {
  const d = (e as { body?: { detail?: unknown } })?.body?.detail;
  if (d && typeof d === 'object') {
    const o = d as { code?: string; message?: string };
    if (o.message) return o.code ? `${o.code}: ${o.message}` : o.message;
  }
  if (typeof d === 'string') return d;
  return e instanceof Error ? e.message : 'Something went wrong';
}

export function useWorldSetup(bookId: string, token: string | null): UseWorldSetup {
  const [run, setRun] = useState<BuildRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blockedBy, setBlockedBy] = useState<BuildRun | null>(null);
  // The poll timer is a SUBSCRIPTION (a real useEffect case), keyed on the run's
  // id + status so it starts/stops with the server-side work.
  const runIdRef = useRef<string | null>(null);
  runIdRef.current = run?.run_id ?? null;

  const call = useCallback(async (fn: () => Promise<BuildRun>) => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      setRun(await fn());
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }, [token]);

  const start = useCallback(async (sourceText: string, modelRef: string, lang: string) => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const created = await worldSetupApi.createRun({
        book_id: bookId,
        params: { model_source: 'user_model', model_ref: modelRef, source_text: sourceText, lang },
      }, token);
      setRun(created);
      setRun(await worldSetupApi.plan(created.run_id, token));   // → plan_ready (checkpoint 1)
    } catch (e) {
      setError(message(e));
      // ACTIVE_RUN is not a failure the author caused, and it is the ONE error with a
      // concrete way out — so find the run that is holding the slot and offer it. Printing
      // the code alone left the panel with no next action, which is how a book got stranded.
      if (message(e).startsWith('ACTIVE_RUN')) {
        try {
          const { items } = await worldSetupApi.list(bookId, token);
          const holder = items.find((r) => BLOCKING.has(r.status)) ?? null;
          setBlockedBy(holder);
        } catch {
          // The lookup is best-effort: failing it must not replace a useful error with a
          // less useful one. The author still sees ACTIVE_RUN, just without the shortcut.
        }
      }
    } finally {
      setBusy(false);
    }
  }, [bookId, token]);

  /** Take over the blocking run — `stepOf` puts the wizard at its checkpoint. */
  const adoptBlocking = useCallback(() => {
    if (!blockedBy) return;
    setRun(blockedBy);
    setBlockedBy(null);
    setError(null);
  }, [blockedBy]);

  const cancelBlocking = useCallback(async () => {
    if (!blockedBy || !token) return;
    setBusy(true);
    try {
      await worldSetupApi.cancel(blockedBy.run_id, token);
      setBlockedBy(null);
      setError(null);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }, [blockedBy, token]);

  const approvePlan = useCallback((worklist: WorklistItem[]) => call(
    () => worldSetupApi.approvePlan(run!.run_id, worklist, token!),
  ), [call, run, token]);

  const projectKg = useCallback(() => call(
    () => worldSetupApi.projectKg(run!.run_id, token!),
  ), [call, run, token]);

  const approveEdges = useCallback((edges: BuildEdge[]) => call(
    () => worldSetupApi.approveEdges(run!.run_id, edges, token!),
  ), [call, run, token]);

  const cancel = useCallback(() => call(
    () => worldSetupApi.cancel(run!.run_id, token!),
  ), [call, run, token]);

  const reset = useCallback(() => { setRun(null); setError(null); }, []);

  // Poll only while the server is actually working.
  useEffect(() => {
    if (!token || !run || !IN_FLIGHT.has(run.status)) return;
    let alive = true;
    const t = setInterval(async () => {
      const id = runIdRef.current;
      if (!id) return;
      try {
        const fresh = await worldSetupApi.get(id, token);
        if (alive) setRun(fresh);
      } catch {
        /* a transient poll failure must not kill the wizard — the next tick retries */
      }
    }, POLL_MS);
    return () => { alive = false; clearInterval(t); };
  }, [token, run, run?.status]);

  return {
    run, busy, error, start, approvePlan, projectKg, approveEdges, cancel, reset,
    blockedBy, adoptBlocking, cancelBlocking,
  };
}
