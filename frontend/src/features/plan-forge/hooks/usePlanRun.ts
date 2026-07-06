// PlanForge controller (M5) — owns the current plan run's lifecycle: create, poll-while-active,
// self-check, validate, compile. No JSX. The poll is the ONE useEffect that syncs on the active
// job (a synchronization concern, not a user-action reaction); user actions are explicit handlers.
import { useCallback, useEffect, useRef, useState } from 'react';
import { planForgeApi, isAck } from '../api';
import {
  isRunPolling,
  type CompilePlanBody,
  type CreatePlanRunBody,
  type PlanCompileResult,
  type PlanRunAck,
  type PlanRunDetail,
  type PlanSelfCheck,
  type PlanValidateReport,
} from '../types';

const POLL_INTERVAL_MS = 2000;

export interface UsePlanRun {
  run: PlanRunDetail | null;
  selfCheck: PlanSelfCheck | null;
  validation: PlanValidateReport | null;
  compileResult: PlanCompileResult | null;
  busy: boolean;
  polling: boolean;
  error: string | null;
  createRun: (body: CreatePlanRunBody) => Promise<void>;
  /** Load an EXISTING run by id (the Runs-list click path) — same slot as createRun's
   * result, just sourced from GET instead of POST. Never touches the server's data. */
  loadRun: (runId: string) => Promise<void>;
  /** Clear the current run back to the empty-propose state (the "+ New propose" path
   * from the Runs list) — local UI state only, no server call. */
  resetRun: () => void;
  runSelfCheck: () => Promise<void>;
  runValidate: () => Promise<void>;
  runCompile: (arcId: string, runPipeline?: boolean, modelRef?: string) => Promise<void>;
}

export function usePlanRun(bookId: string, token: string | null): UsePlanRun {
  const [run, setRun] = useState<PlanRunDetail | null>(null);
  const [selfCheck, setSelfCheck] = useState<PlanSelfCheck | null>(null);
  const [validation, setValidation] = useState<PlanValidateReport | null>(null);
  const [compileResult, setCompileResult] = useState<PlanCompileResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A generation guard: a create/reset bumps this so a stale poll tick never re-sets an old run.
  const genRef = useRef(0);

  const polling = run ? isRunPolling(run) : false;

  // Poll the run detail while its job is active. Synchronization effect: it mirrors the server's
  // job state into local state and clears its own timer on unmount / terminal / run change. When
  // the job settles (isRunPolling false) the effect re-runs and installs no timer → the loop stops.
  useEffect(() => {
    if (!token || !run || !isRunPolling(run)) return;
    const runId = run.id;
    const gen = genRef.current;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const next = await planForgeApi.getRun(bookId, runId, token);
        if (cancelled || genRef.current !== gen) return;
        setRun(next);
      } catch (e) {
        if (cancelled || genRef.current !== gen) return;
        setError((e as Error).message);
      }
    }, POLL_INTERVAL_MS);
    return () => { cancelled = true; clearTimeout(timer); };
    // Re-arm on every run object change (a poll setRun produces a new object → next tick).
  }, [bookId, token, run]);

  const createRun = useCallback(async (body: CreatePlanRunBody) => {
    if (!token) return;
    const gen = ++genRef.current;
    setBusy(true);
    setError(null);
    setSelfCheck(null);
    setValidation(null);
    setCompileResult(null);
    try {
      const resp = await planForgeApi.createRun(bookId, body, token);
      if (genRef.current !== gen) return;
      // llm → 202 ack (not a full detail): fetch the detail so the poll has active_job_id/status.
      // rules → 201 full detail: use it directly.
      let detail: PlanRunDetail;
      if (isAck(resp)) {
        detail = await planForgeApi.getRun(bookId, (resp as PlanRunAck).run_id, token);
      } else {
        detail = resp as PlanRunDetail;
      }
      if (genRef.current !== gen) return;
      setRun(detail);
    } catch (e) {
      if (genRef.current === gen) setError((e as Error).message);
    } finally {
      if (genRef.current === gen) setBusy(false);
    }
  }, [bookId, token]);

  const loadRun = useCallback(async (runId: string) => {
    if (!token) return;
    const gen = ++genRef.current;
    setBusy(true);
    setError(null);
    setSelfCheck(null);
    setValidation(null);
    setCompileResult(null);
    try {
      const detail = await planForgeApi.getRun(bookId, runId, token);
      if (genRef.current !== gen) return;
      setRun(detail);
    } catch (e) {
      if (genRef.current === gen) setError((e as Error).message);
    } finally {
      if (genRef.current === gen) setBusy(false);
    }
  }, [bookId, token]);

  const resetRun = useCallback(() => {
    ++genRef.current; // invalidate any in-flight poll/load so it can't resurrect the old run
    setRun(null);
    setSelfCheck(null);
    setValidation(null);
    setCompileResult(null);
    setError(null);
  }, []);

  const runSelfCheck = useCallback(async () => {
    if (!token || !run) return;
    setBusy(true);
    setError(null);
    try {
      const r = await planForgeApi.selfCheck(bookId, run.id, token);
      setSelfCheck(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [bookId, token, run]);

  const runValidate = useCallback(async () => {
    if (!token || !run) return;
    setBusy(true);
    setError(null);
    try {
      const r = await planForgeApi.validate(bookId, run.id, token);
      setValidation(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [bookId, token, run]);

  const runCompile = useCallback(async (arcId: string, runPipeline?: boolean, modelRef?: string) => {
    if (!token || !run) return;
    setBusy(true);
    setError(null);
    try {
      const body: CompilePlanBody = { arc_id: arcId };
      if (runPipeline !== undefined) body.run_pipeline = runPipeline;
      if (modelRef) body.model_ref = modelRef;
      const r = await planForgeApi.compile(bookId, run.id, body, token);
      // A 202 ack means the pipeline runs async — re-fetch the run so its status reflects it;
      // an inline compile package is the result to show.
      if (isAck(r)) {
        const detail = await planForgeApi.getRun(bookId, run.id, token);
        setRun(detail);
      } else {
        setCompileResult(r as PlanCompileResult);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [bookId, token, run]);

  return {
    run, selfCheck, validation, compileResult, busy, polling, error,
    createRun, loadRun, resetRun, runSelfCheck, runValidate, runCompile,
  };
}
