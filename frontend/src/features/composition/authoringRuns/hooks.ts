// #20_agent_mode.md — react-query hooks over authoringRunsApi. Polling pattern
// mirrors useCampaignQueries.ts (this repo's established sibling for a run-like
// FSM entity): `refetchInterval: (query) => isActive(...) ? ms : false`.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { authoringRunsApi } from './api';
import { ACTIVE_RUN_STATUSES } from './fsm';
import type { AuthoringRunStatus, CreateAuthoringRunBody } from './types';

const POLL_MS = 5000; // matches the mockup's documented "polling every 5s" cadence

function isPolling(status?: AuthoringRunStatus): boolean {
  return !!status && (ACTIVE_RUN_STATUSES.includes(status) || status === 'draft');
}

export function useAuthoringRunsList(bookId: string) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['authoring-runs', bookId],
    queryFn: () => authoringRunsApi.list(bookId, accessToken!),
    enabled: !!accessToken && !!bookId,
  });
}

/** The book's active (gated/running/paused) run, if any — used to pre-empt
 * "+ New run" client-side (never rely on the create call's 409 alone). */
export function useActiveAuthoringRun(bookId: string) {
  const list = useAuthoringRunsList(bookId);
  const active = list.data?.items.find((r) => ACTIVE_RUN_STATUSES.includes(r.status)) ?? null;
  return { active, ...list };
}

export function useAuthoringRun(runId: string | null) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['authoring-run', runId],
    queryFn: () => authoringRunsApi.get(runId!, accessToken!),
    enabled: !!accessToken && !!runId,
    refetchInterval: (q) => (isPolling(q.state.data?.status) ? POLL_MS : false),
  });
}

export function useAuthoringRunReport(runId: string | null, enabled: boolean) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['authoring-run-report', runId],
    queryFn: () => authoringRunsApi.report(runId!, accessToken!),
    enabled: !!accessToken && !!runId && enabled,
  });
}

/** Every mutation invalidates BOTH the run detail and the book's run list (a
 * status transition changes both the mission-control view and the runs table). */
export function useAuthoringRunMutations(bookId: string, runId: string | null) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['authoring-runs', bookId] });
    qc.invalidateQueries({ queryKey: ['authoring-run', runId] });
    qc.invalidateQueries({ queryKey: ['authoring-run-report', runId] });
  };

  const create = useMutation({
    mutationFn: (body: CreateAuthoringRunBody) => authoringRunsApi.create(body, accessToken!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['authoring-runs', bookId] }),
  });
  const gate = useMutation({
    mutationFn: () => authoringRunsApi.gate(runId!, accessToken!),
    onSuccess: invalidate,
  });
  const start = useMutation({
    mutationFn: () => authoringRunsApi.start(runId!, accessToken!),
    onSuccess: invalidate,
  });
  const pause = useMutation({
    mutationFn: () => authoringRunsApi.pause(runId!, accessToken!),
    onSuccess: invalidate,
  });
  const resume = useMutation({
    mutationFn: () => authoringRunsApi.resume(runId!, accessToken!),
    onSuccess: invalidate,
  });
  const close = useMutation({
    mutationFn: () => authoringRunsApi.close(runId!, accessToken!),
    onSuccess: invalidate,
  });
  const setPausePolicy = useMutation({
    mutationFn: (pauseAfterEachUnit: boolean) =>
      authoringRunsApi.setPausePolicy(runId!, pauseAfterEachUnit, accessToken!),
    onSuccess: invalidate,
  });
  const acceptUnit = useMutation({
    mutationFn: (unitIndex: number) => authoringRunsApi.acceptUnit(runId!, unitIndex, accessToken!),
    onSuccess: invalidate,
  });
  const rejectUnit = useMutation({
    mutationFn: (unitIndex: number) => authoringRunsApi.rejectUnit(runId!, unitIndex, accessToken!),
    onSuccess: invalidate,
  });
  const revertAll = useMutation({
    mutationFn: () => authoringRunsApi.revertAll(runId!, accessToken!),
    onSuccess: invalidate,
  });

  return { create, gate, start, pause, resume, close, setPausePolicy, acceptUnit, rejectUnit, revertAll };
}

export function useAuthoringRunAccessToken(): string | null {
  return useAuth().accessToken;
}
