// P4 — Unified Jobs GUI. TS types mirroring the loreweave_jobs SDK contract
// (sdks/python/loreweave_jobs/contract.py) as serialized by jobs-service.

/** Canonical job lifecycle status (JobStatus enum). */
export type JobStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'cancelling'
  | 'completed'
  | 'failed'
  | 'cancelled';

/** Terminal statuses — no control is ever valid. */
export const TERMINAL_STATUSES: readonly JobStatus[] = ['completed', 'failed', 'cancelled'];

export function isTerminal(status: JobStatus): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status);
}

/** State-aware control capability (ControlCap enum). */
export type ControlCap = 'cancel' | 'pause' | 'resume';
export type JobControlAction = ControlCap;

export type JobProgress = { done: number; total: number };
export type JobError = { code: string; message: string };

/** One job projection row as returned by GET /v1/jobs and /v1/jobs/{service}/{job_id}. */
export interface Job {
  service: string;
  job_id: string;
  owner_user_id: string;
  kind: string;
  status: JobStatus;
  parent_job_id: string | null;
  detail_status: string | null;
  progress: JobProgress | null;
  /** Recomputed per row at read time — re-read on every SSE event, never cache per-kind. */
  control_caps: ControlCap[];
  title: string | null;
  error: JobError | null;
  created_at: string | null; // ISO-8601 UTC
  updated_at: string | null; // ISO-8601 UTC
  /** Only meaningful in list/detail (parent view); absent on the SSE stream. */
  child_count?: number | null;
}

/** SSE frame from GET /v1/jobs/stream — the Job shape minus created_at/child_count. */
export type JobSseEvent = Omit<Job, 'created_at' | 'child_count'>;

export interface JobListResponse {
  items: Job[];
  next_cursor: string | null;
}

export interface JobListParams {
  status?: JobStatus | '';
  kind?: string | '';
  /** List children of this parent job; omit for top-level only. */
  parent?: string;
  q?: string;
  cursor?: string;
  limit?: number;
}

/** Stable key for a job across list/overlay (PK = service + job_id). */
export function jobKey(j: { service: string; job_id: string }): string {
  return `${j.service}:${j.job_id}`;
}
