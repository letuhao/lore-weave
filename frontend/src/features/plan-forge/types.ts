// PlanForge (Writing-Studio M5) — the novel-system planner over composition-service's
// /v1/composition/books/{bookId}/plan REST surface. Types mirror the contract exactly.

export type PlanRunMode = 'rules' | 'llm';

// The run's lifecycle. `pending` is the transient llm-worker state (an active job); the rest
// are terminal-ish states the detail settles into.
export type PlanRunStatus =
  | 'pending'
  | 'proposed'
  | 'checkpoint'
  | 'validated'
  | 'compiled'
  | 'failed';

export type PlanArtifactKind = string; // 'novel_system_spec' | 'fidelity_report' | … (open enum)

export interface PlanArtifact {
  kind: PlanArtifactKind;
  artifact_id: string;
}

// GET /runs/{runId} — the canonical run detail. `active_job_id`/`job_status` drive the poll:
// while a job is pending|running the FE re-fetches; on terminal it stops.
export interface PlanRunDetail {
  id: string;
  book_id: string;
  status: PlanRunStatus;
  mode: PlanRunMode;
  model_ref: string | null;
  source_checksum: string | null;
  active_job_id: string | null;
  job_status: string | null; // pending | running | completed | failed | null (rules → no job)
  error_detail: string | null;
  checkpoint_state: Record<string, unknown> | null;
  artifacts: PlanArtifact[];
  created_at: string;
  updated_at: string;
}

// POST /runs (llm) → 202 acknowledgement; (rules) → 201 full PlanRunDetail. The api layer
// normalizes both to a PlanRunDetail-ish handle carrying at least `id`.
export interface PlanRunAck {
  run_id: string;
  job_id: string;
  status: PlanRunStatus;
}

// POST /runs/{runId}/validate
export interface PlanValidateRule {
  id: string;
  passed: boolean;
  message: string;
}
export interface PlanValidateReport {
  passed: boolean;
  rules: PlanValidateRule[];
  fidelity_score: number | null; // null when the fidelity config is absent (v1 fixture-based)
  fidelity_report_id: string | null;
}

// POST /runs/{runId}/self-check
export type PlanGapSeverity = string; // 'error' | 'warning' | 'info' (open)
export interface PlanGap {
  path: string;
  severity: PlanGapSeverity;
  message: string;
}
export interface PlanSelfCheck {
  gaps: PlanGap[];
  fidelity_score: number | null; // null when the fidelity config is absent (v1 fixture-based)
}

// POST /runs/{runId}/refine
export interface PlanRefineResult {
  status: 'applied' | 'no_change' | 'rejected';
  spec_artifact_id: string;
  fidelity_delta: number;
  diagnosis: string;
}

// POST /runs/{runId}/interpret — the interpretation object is loosely shaped by the BE.
export type PlanInterpretation = Record<string, unknown>;

// POST /runs/{runId}/compile
export interface PlanCompileResult {
  package: Record<string, unknown>;
  pipeline_job_id: string;
  work_id: string;
}

// GET /runs list page
export interface PlanRunListPage {
  items: PlanRunDetail[];
  next_cursor: string | null;
}

// Request bodies.
export interface CreatePlanRunBody {
  source_markdown: string;
  mode: PlanRunMode;
  model_ref?: string; // REQUIRED when mode === 'llm'
  force?: boolean;
}
export interface RefinePlanBody {
  model_ref: string;
  revision?: string;
  focus_paths?: string[];
}
export interface InterpretPlanBody {
  user_message: string;
  model_ref: string;
  apply_mode_hint?: string;
}
export interface CompilePlanBody {
  arc_id: string;
  run_pipeline?: boolean;
  model_ref?: string;
}

/** A job/run status is "settled" (poll can stop) unless it's actively running. */
export function isRunPolling(detail: Pick<PlanRunDetail, 'active_job_id' | 'job_status'>): boolean {
  if (!detail.active_job_id) return false;
  const s = detail.job_status;
  return s === 'pending' || s === 'running';
}
