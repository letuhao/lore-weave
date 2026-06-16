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

/** Dynamic, whitelisted parameters the producer attached to the job (P4 `params`
 *  JSONB). Rendered as-is in the detail Parameters panel — model now, effort later,
 *  no schema change. Values are scalars or short arrays; never the raw prompt/secret. */
export type JobParams = Record<string, unknown>;

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
  // P4 usage fields — model is the resolved NAME (not the ref-UUID); cost_usd is
  // reliable; tokens_in/out are best-effort (nullable). All COALESCE-merged on the
  // projection, so a later event without them never wipes the accumulated value.
  model: string | null;
  cost_usd: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
  params: JobParams | null;
  created_at: string | null; // ISO-8601 UTC
  updated_at: string | null; // ISO-8601 UTC
  /** Only meaningful in list/detail (parent view); absent on the SSE stream. */
  child_count?: number | null;
}

/** SSE frame from GET /v1/jobs/stream — the Job shape minus created_at/child_count
 *  (the live event carries model/cost/tokens/params so rows update without refetch). */
export type JobSseEvent = Omit<Job, 'created_at' | 'child_count'>;

export interface JobListResponse {
  items: Job[];
  next_cursor: string | null;
  /** Set only in offset (History) mode — the total row count for the "X–Y of N" pager. */
  total: number | null;
}

/** Owner-scoped top-level status counts for the 4 summary cards (GET /v1/jobs/summary). */
export interface JobSummary {
  active: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface JobListParams {
  status?: JobStatus | '';
  kind?: string | '';
  /** List children of this parent job; omit for top-level only. */
  parent?: string;
  q?: string;
  /** 'active' (non-terminal, keyset/live) | 'history' (terminal, offset+total). */
  bucket?: 'active' | 'history';
  cursor?: string;
  /** Offset mode (History) — when set, the response returns `total`. */
  offset?: number;
  limit?: number;
}

/** Stable key for a job across list/overlay (PK = service + job_id). */
export function jobKey(j: { service: string; job_id: string }): string {
  return `${j.service}:${j.job_id}`;
}
