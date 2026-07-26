// #20_agent_mode.md — types mirroring composition-service's authoring-run REST
// contract (services/composition-service/app/routers/authoring_runs.py
// `_serialize`/`_serialize_unit` + app/db/models.py AuthoringRun/AuthoringRunUnit,
// ground-truth table). Some fields (`driver_id`, `driver_heartbeat_at`,
// `pause_after_each_unit`) are D4/D11 additions the backend is landing in
// parallel — declared optional here so this FE builds against the target
// contract without crashing against a not-yet-updated server response.

export const AUTHORING_RUN_STATUSES = [
  'draft', 'gated', 'running', 'paused', 'failed', 'report_ready', 'closed',
] as const;
export type AuthoringRunStatus = typeof AUTHORING_RUN_STATUSES[number];

export const AUTHORING_RUN_UNIT_STATUSES = [
  'pending', 'drafted', 'failed', 'accepted', 'rejected',
] as const;
export type AuthoringRunUnitStatus = typeof AUTHORING_RUN_UNIT_STATUSES[number];

export type CriticSeverity = 'ok' | 'warn' | 'severe';

export interface CriticVerdict {
  severity: CriticSeverity;
  summary: string;
  cost_usd: string;
  detail?: Record<string, unknown> | null;
}

export interface AuthoringRun {
  run_id: string;
  book_id: string;
  plan_run_id: string;
  level: number;
  scope: string[]; // ordered chapter-id strings
  budget_usd: string;
  spent_usd: string;
  tool_allowlist: string[];
  params: Record<string, unknown>;
  breaker_state: Record<string, unknown>;
  status: AuthoringRunStatus;
  current_unit: number;
  error_message: string | null;
  background: boolean;
  created_at: string | null;
  updated_at: string | null;
  // D4/D11 — real model fields; optional until the backend's serializer lands them.
  driver_id?: string | null;
  driver_heartbeat_at?: string | null;
  // D4/D4a — server-enforced auto-pause flag. Optional/undefined = server hasn't
  // shipped the column yet; the FE must not assume a default it can't observe.
  pause_after_each_unit?: boolean;
}

export interface AuthoringRunUnit {
  run_id: string;
  unit_index: number;
  chapter_id: string;
  status: AuthoringRunUnitStatus;
  pre_revision_id: string | null;
  post_revision_id: string | null;
  cost_usd: string;
  error_message: string | null;
  critic_verdict: CriticVerdict | null;
  created_at: string | null;
  updated_at: string | null;
}

/** GET /{run_id}/report row — unit_report() over the FULL scope (unattempted
 * units synthesized as 'pending'). */
export interface AuthoringRunUnitReportRow extends AuthoringRunUnit {
  downstream_unit_indexes: number[];
}

export interface AuthoringRunReport {
  run: AuthoringRun;
  units: AuthoringRunUnitReportRow[];
  dependencies: { model: string; note: string };
}

export interface RejectUnitResult extends AuthoringRunUnit {
  reverted: boolean;
  cascade_warning: { downstream_unit_indexes: number[]; note: string };
}

export interface RevertAllResult {
  reverted_unit_indexes: number[];
  failed_unit_index: number | null;
  error: string | null;
  run_status: string;
  closed: boolean;
}

export interface CreateAuthoringRunBody {
  book_id: string;
  plan_run_id: string;
  level: 3 | 4;
  scope: string[];
  budget_usd: string;
  tool_allowlist: string[];
  params?: Record<string, unknown>;
  background?: boolean;
  // D4b — no default: the caller must say whether this run pauses after every
  // unit. Included optimistically; a not-yet-updated server just ignores it
  // (pydantic BaseModel ignores unknown fields by default).
  pause_after_each_unit: boolean;
}
