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
  extraction_enabled: boolean;
  extraction_status: ExtractionStatus;
  embedding_model: string | null;
  // K12.4: dimension derived from embedding_model server-side.
  embedding_dimension: number | null;
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
}

export interface ProjectUpdatePayload {
  name?: string;
  description?: string;
  instructions?: string;
  // book_id: omit to leave unchanged; null to clear; UUID to set.
  book_id?: string | null;
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
}

export interface ProjectListResponse {
  items: Project[];
  next_cursor: string | null;
}

export interface ProjectListParams {
  limit?: number;
  cursor?: string | null;
  include_archived?: boolean;
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
}
