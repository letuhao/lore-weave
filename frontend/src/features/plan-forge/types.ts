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

// BE-3 — GET /runs/{runId}/artifacts/{artifactId}: one artifact's CONTENT (the run detail /
// pass ledger carry only refs). The Pass Rail loads this to render what a checkpoint approves.
export interface PlanArtifactDetail {
  artifact_id: string;
  kind: string;
  content: unknown;
  created_at: string | null;
}

// D-PLANFORGE-ARC-PICKER: the spec's own arcs, {id, title} — lets Compile offer a
// picker instead of a bare arc_id text box a writer has no way to fill in correctly.
export interface PlanArc {
  id: string;
  title: string;
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
  // BE-3b — the braindump this run was proposed from, so reopening a run restores the textarea.
  source_markdown: string | null;
  is_archived?: boolean; // BE-4 — soft-archived; the runs list offers restore instead of archive
  active_job_id: string | null;
  job_status: string | null; // pending | running | completed | failed | null (rules → no job)
  error_detail: string | null;
  checkpoint_state: Record<string, unknown> | null;
  arcs: PlanArc[]; // [] before a spec exists yet — never missing, so the FE never has to guess
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
  pipeline_job_id: string | null;
  work_id: string;
}

// ── 27 V2 · the 7-pass compiler ledger (GET /runs/{runId}/passes) ──────────────────
// The pass rail's data. `fresh`, `pass_cursor`, `blocked_at`, `blockers` are all DERIVED at
// serialization server-side (PF-3) — never stored, so they can't go stale about staleness.
export type PlanPassCheckpoint = 'blocking' | 'advisory';
export type PlanPassId =
  | 'motifs' | 'cast' | 'world' | 'beats' | 'character_arcs' | 'scenes' | 'self_heal';

export interface PlanPass {
  pass_id: PlanPassId;
  checkpoint: PlanPassCheckpoint;
  output_kind: string;
  depends_on: string[];
  status: string;   // 'pending' | 'running' | 'completed' | 'failed'
  decision: string; // 'pending' | 'accepted' | 'auto' | 'rejected'
  artifact_id: string | null;
  job_id: string | null;
  fresh: boolean;
  blockers: string[];
  // BE-20 — only present once that slice lands; the checkpoint review needs it (PF-7).
  bootstrap_proposal_id?: string | null;
  decided_by?: string | null;
  decided_at?: string | null;
}

export interface PlanPassLedger {
  run_id: string;
  book_id: string;
  genre_tags: string[];
  // Absent ≠ zero: a run that never compiled has NO package, so every package-reading pass is
  // un-runnable. The rail says "compile first" rather than showing 7 tidy pending rows.
  compiled: boolean;
  passes: PlanPass[];
  pass_cursor: number;      // how far the compiler can proceed unattended (contiguous fresh+accepted)
  blocked_at: PlanPassId | null; // the first blocking pass waiting on a human
}

export interface RunPassBody {
  model_ref?: string;
  params?: Record<string, unknown>;
  force?: boolean;
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
  // PS-5 — the backend deep-merges this as a PATCH dict (plan_forge.py PlanRefineRequest.revision:
  // dict). It was typed `string` here, drifted since the method was written with zero callers, so
  // the first person to wire a refine button got a 422 and debugged the button. Fixed with the wiring.
  revision?: Record<string, unknown>;
  focus_paths?: string[];
}

// BE-2 — POST /autofix result: the applied rounds + the fresh run detail.
export interface PlanAutofixRound {
  round: number;
  targets: number;
  result: string; // 'applied' | 'no_change' | …
}
export interface PlanAutofixResult {
  rounds: PlanAutofixRound[];
  run: PlanRunDetail;
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

// ── Auto-bootstrap gate (M4, docs/specs/2026-07-06-planforge-auto-bootstrap.md §6) ──
// propose -> record -> approve -> apply: the LLM/deterministic diff runs ONCE (propose),
// a human reviews + approves, apply is a separate deterministic replay. Never re-propose
// on retry — the FE must not call propose() again just because apply() is being retried.
export type BootstrapStatus = 'pending' | 'approved' | 'rejected' | 'applying' | 'applied' | 'failed';

export interface BootstrapNewChapter {
  event_id: string;
  title: string;
  ordinal: number | null;
  drafting_guide?: string; // M3 — a plain-text scene/beat synopsis, when a pipeline job supplied one
}

export interface BootstrapNewGlossaryEntity {
  name: string;
  kind_code: string; // 'character' | 'concept' | … (open — mirrors glossary's own kind codes)
  attributes: Record<string, unknown>;
}

export interface BootstrapDiff {
  new_chapters: BootstrapNewChapter[];
  new_glossary_entities: BootstrapNewGlossaryEntity[];
}

// applied_results is keyed by event_id (chapters) or `glossary:{kind_code}:{name}` (entities) —
// the FE never constructs these keys itself, only reads them back to show "done" state.
export interface BootstrapAppliedChapterResult {
  chapter_id: string;
  title: string;
  drafting_guide?: string;
}
export interface BootstrapAppliedGlossaryResult {
  entity_id: string;
  name: string;
  kind_code: string;
  status: string; // 'created' | 'updated' | 'skipped'
}
export type BootstrapAppliedResult = BootstrapAppliedChapterResult | BootstrapAppliedGlossaryResult;

export interface BootstrapProposal {
  id: string;
  run_id: string;
  book_id: string;
  owner_user_id: string;
  status: BootstrapStatus;
  diff: BootstrapDiff;
  applied_results: Record<string, BootstrapAppliedResult>;
  error_detail: string | null;
  created_at: string;
  updated_at: string;
}
