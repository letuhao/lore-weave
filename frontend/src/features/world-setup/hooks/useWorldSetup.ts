// World Setup controller — owns ALL pipeline logic + state; the panel only renders.
// (Frontend MVC: hooks are controllers, components are views.)
import { useCallback, useEffect, useRef, useState } from 'react';

import { worldSetupApi } from '../api';
import type { BuildEdge, BuildRun, WorklistItem } from '../types';

/** Statuses where the server is still working — the only ones worth polling. */
const IN_FLIGHT = new Set(['planning', 'building', 'proposing', 'kg_projecting']);
const POLL_MS = 4000;

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
    } finally {
      setBusy(false);
    }
  }, [bookId, token]);

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

  return { run, busy, error, start, approvePlan, projectKg, approveEdges, cancel, reset };
}
