// Mirrors services/knowledge-service/app/db/models.py.
// Track 1 surface only: extraction_* fields are present because the API
// returns them, but K8 Track 1 FE renders them as "disabled" (see
// SESSION_PATCH D-K8-02). Track 2 UI will consume the other states.

export type ProjectType = 'book' | 'translation' | 'code' | 'general';

export type ExtractionStatus =
  | 'disabled'
  | 'building'
  | 'paused'
  | 'ready'
  | 'failed';

export type ScopeType = 'global' | 'project' | 'session' | 'entity';

export interface Project {
  project_id: string;
  user_id: string;
  name: string;
  description: string;
  project_type: ProjectType;
  book_id: string | null;
  instructions: string;
  genre: string | null;
  extraction_enabled: boolean;
  // K21-C (D3 / K21.12): when false, the chat tool loop skips this
  // project's memory tools entirely. Default true (the BE Cycle-B
  // column). PATCH /v1/knowledge/projects/{id} already accepts it.
  tool_calling_enabled: boolean;
  // K21-C (D4 / K21.7 sf4): when true, a `memory_remember` tool call
  // queues a pending fact for the user to confirm/reject instead of
  // writing it straight to the graph. Default false — opt-in.
  memory_remember_confirm: boolean;
  // WS-4C Half A: when true, every 4th chat turn is sent to glossary to
  // extract the entities it newly NAMED, which land in the book's review
  // inbox as ai-suggested drafts (never canon). Default false — OPT-IN,
  // because each capture is an LLM call billed to the user's own model.
  canon_capture_enabled: boolean;
  extraction_status: ExtractionStatus;
  embedding_model: string | null;
  // K12.4: dimension derived from embedding_model server-side.
  embedding_dimension: number | null;
  // D-RERANK-NOT-BYOK: per-project BYOK rerank model (provider-registry
  // user_model UUID) + source. null ⇒ raw-search skips the rerank step.
  rerank_model: string | null;
  rerank_model_source: string;
  extraction_config: Record<string, unknown>;
  last_extracted_at: string | null;
  estimated_cost_usd: string;
  actual_cost_usd: string;
  is_archived: boolean;
  // D-K8-03: bumped on every non-empty PATCH. FE captures it on
  // dialog open and sends it back in If-Match to detect lost updates.
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreatePayload {
  name: string;
  description?: string;
  project_type: ProjectType;
  book_id?: string | null;
  instructions?: string;
  genre?: string | null;
}

export interface ProjectUpdatePayload {
  name?: string;
  description?: string;
  instructions?: string;
  // book_id: omit to leave unchanged; null to clear; UUID to set.
  book_id?: string | null;
  // genre: omit to leave unchanged; null to clear; string to set.
  genre?: string | null;
  // K-CLEAN-3 (D-K8-02 partial): the K7c PATCH endpoint accepts
  // is_archived for the Restore action. Setting to false on an
  // archived row un-archives it. Track 1 only ships the restore
  // direction from the FE (set false); archive uses the dedicated
  // POST /archive endpoint.
  is_archived?: boolean;
  // K12.4: embedding_model governs which vector space the project's
  // :Passage nodes live in (consumed by K18.3 L3 semantic search).
  // Omit to leave unchanged; null to clear; a known model name to set.
  // The backend auto-derives embedding_dimension from the model name.
  embedding_model?: string | null;
  // D-RERANK-NOT-BYOK (S0b): per-project BYOK rerank model — a
  // provider-registry user_model UUID. Omit to leave unchanged; null to
  // clear (rerank then skipped in raw-search).
  rerank_model?: string | null;
  // K21-C (D3): per-project memory-tool opt-out. Omit to leave
  // unchanged. The public PATCH endpoint accepted this since Cycle B.
  tool_calling_enabled?: boolean;
  // K21-C (D4): per-project `memory_remember` confirmation gate.
  // Omit to leave unchanged.
  memory_remember_confirm?: boolean;
  // WS-4C Half A: per-project canon auto-capture. Omit to leave unchanged.
  canon_capture_enabled?: boolean;
}

export interface ProjectListResponse {
  items: Project[];
  next_cursor: string | null;
}

// ── B2-B/C — per-novel extraction-config tuning ────────────────────────────
// Mirrors knowledge-service ProjectExtractionConfigUpdate (PUT-replace). The
// FE does read-modify-write off the project's existing extraction_config so it
// never drops keys it doesn't expose. `writer_autocreate` is intentionally NOT
// surfaced yet (resolved+hashed BE-side but not applied — would be misleading).
export type ExtractionModelSource = 'user_model' | 'platform_model';
export type FilterCategory = 'entity' | 'relation' | 'event';
export type PartialPolicy = 'keep' | 'drop';
export type PromptOp = 'entity' | 'relation' | 'event' | 'fact';
export const PROMPT_OPS: PromptOp[] = ['entity', 'relation', 'event', 'fact'];
// Matches the BE 16 kB/field cap (loreweave/knowledge ProjectExtractionConfigUpdate).
export const PROMPT_MAX_LEN = 16384;

export interface PrecisionFilterOverride {
  enabled?: boolean;
  categories?: FilterCategory[];
  partial_policy?: PartialPolicy;
  model_ref?: string;
  model_source?: ExtractionModelSource;
}

export interface EntityRecoveryOverride {
  enabled?: boolean;
  model_ref?: string;
  model_source?: ExtractionModelSource;
  // KN model-roles — Tier-3 classifier batch size (1-20; omit = default 5).
  max_items_per_batch?: number;
}

export interface PromptOverride {
  system?: string;
}

export interface ExtractionConfigPayload {
  llm_model?: { model_ref?: string; model_source?: ExtractionModelSource };
  precision_filter?: PrecisionFilterOverride;
  entity_recovery?: EntityRecoveryOverride;
  writer_autocreate?: { enabled?: boolean };
  prompts?: Partial<Record<PromptOp, PromptOverride>>;
}

// C7-followup (KN-7) — server-side narrowing. `sort_by` / `status` are
// CLOSED allowlists that mirror the BE Literals; an out-of-set value 422s.
export type ProjectSortBy = 'created_at' | 'updated_at' | 'name' | 'status';
export type ProjectSortDir = 'asc' | 'desc';
// The five extraction lifecycle states plus the `archived` pseudo-state.
export type ProjectStatusFilter = ExtractionStatus | 'archived';

export interface ProjectListParams {
  limit?: number;
  cursor?: string | null;
  include_archived?: boolean;
  // ARCH-1 C5: filter to the project linked to this book (editor AI panel).
  book_id?: string;
  // C7-followup: server-side search / sort / status. The browser narrows
  // across ALL projects, not just the loaded cursor pages.
  search?: string;
  sort_by?: ProjectSortBy;
  sort_dir?: ProjectSortDir;
  status?: ProjectStatusFilter;
}

export interface Summary {
  summary_id: string;
  user_id: string;
  scope_type: ScopeType;
  scope_id: string | null;
  content: string;
  token_count: number | null;
  version: number;
  created_at: string;
  updated_at: string;
}

// D-K8-01: an archived pre-update snapshot of a summary row.
// Created automatically by the repo on every successful update
// and by the rollback endpoint. `edit_source` distinguishes a
// user-typed update from a rollback operation — the History
// panel renders them differently.
export type SummaryEditSource = 'manual' | 'rollback';

export interface SummaryVersion {
  version_id: string;
  summary_id: string;
  user_id: string;
  version: number;
  content: string;
  token_count: number | null;
  created_at: string;
  edit_source: SummaryEditSource;
}

export interface SummaryVersionListResponse {
  items: SummaryVersion[];
}

export interface SummariesListResponse {
  // JSON field is "global" (aliased on backend). TS keyword is not a
  // problem as a property name but kept identical to the wire format.
  global: Summary | null;
  projects: Summary[];
}

export interface SummaryUpdatePayload {
  content: string;
}

export interface UserDataDeleteResponse {
  deleted: {
    summaries: number;
    projects: number;
  };
}

export interface UserDataExportBundle {
  schema_version: number;
  user_id: string;
  exported_at: string;
  projects: Project[];
  summaries: Summary[];
}

// ── T2-close-1b-FE — K17.9 benchmark status ─────────────────────────────
// Mirrors services/knowledge-service/app/routers/internal_benchmark.py
// BenchmarkStatusResponse. Used by the EmbeddingModelPicker badge.
// `has_run=false` is a valid state (renders a neutral "no benchmark
// yet" badge), NOT an error.
export interface BenchmarkStatus {
  has_run: boolean;
  passed: boolean | null;
  run_id: string | null;
  embedding_model: string | null;
  recall_at_3: number | null;
  mrr: number | null;
  created_at: string | null;
  // R2 (D-JOURNEY-KG-BENCHMARK-UX) — named failing gates on the latest run
  // (empty == passed). `insufficient_runs` means inconclusive (too few passes),
  // NOT a low-quality model; the badge keys its copy off this so it never says
  // "low-quality" when recall@3 is actually fine. Optional (older BE omits it).
  gate_failures?: string[];
}

// ── C12b-b — K17.9 on-demand benchmark run ─────────────────────────────
// Mirrors services/knowledge-service/app/routers/public/extraction.py
// BenchmarkRunResponse (C12b-a BE shape). Returned by the synchronous
// POST /v1/knowledge/projects/{id}/benchmark-run endpoint. Full
// `raw_report` lives in `project_embedding_benchmark_runs` and is
// reachable via GET /benchmark-status; the FE keeps the wire shape
// lean for the Run-benchmark button flow.
export interface BenchmarkRunResponse {
  run_id: string;
  embedding_model: string;
  passed: boolean;
  recall_at_3: number;
  mrr: number;
  avg_score_positive: number;
  negative_control_max_score: number;
  stddev_recall: number;
  stddev_mrr: number;
  // The effective run count (the interactive endpoint clamps up to min_runs, so
  // a requested runs=1 reports runs=3 — a perfect short run no longer "fails").
  runs: number;
  // R2 — named failing gates (empty == passed). See BenchmarkStatus.gate_failures.
  gate_failures?: string[];
}
