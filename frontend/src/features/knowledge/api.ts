import { apiJson } from '../../api';
import type {
  BenchmarkStatus,
  Project,
  ProjectCreatePayload,
  ProjectListParams,
  ProjectListResponse,
  ProjectUpdatePayload,
  SummariesListResponse,
  Summary,
  SummaryUpdatePayload,
  SummaryVersion,
  SummaryVersionListResponse,
  UserDataDeleteResponse,
} from './types';
import type {
  CostEstimate,
  ExtractionJobStatus,
} from './types/projectState';

// ── K19a.4 — Extraction wire types ───────────────────────────────────────
// Mirrors services/knowledge-service/app/db/repositories/extraction_jobs.py.
// Note: BE ships `scope` as a bare string literal, not the UI's
// discriminated-union JobScope. The hook converts between the two.
export type ExtractionJobScopeWire =
  | 'all'
  | 'chapters'
  | 'chat'
  | 'glossary_sync';

export interface ExtractionJobWire {
  job_id: string;
  user_id: string;
  project_id: string;
  scope: ExtractionJobScopeWire;
  scope_range: Record<string, unknown> | null;
  status: ExtractionJobStatus;
  llm_model: string;
  embedding_model: string;
  max_spend_usd: string | null;
  items_processed: number;
  items_total: number | null;
  cost_spent_usd: string;
  current_cursor: Record<string, unknown> | null;
  started_at: string;
  paused_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  error_message: string | null;
  /**
   * K19b.2: populated only by `knowledgeApi.listAllJobs`. Per-project
   * routes (`listExtractionJobs`) and the single-job detail route
   * leave this `null`; those callers already have the project in
   * scope, so the BE skips the LEFT JOIN. Consumers that need the
   * name from a per-project context should read it from the Project
   * object directly, not this field.
   */
  project_name: string | null;
  /**
   * C6 (D-K19b.3-01) — human-readable chapter title for the job's
   * current cursor position. Present when `current_cursor.last_chapter_id`
   * is set AND book-service resolved it successfully. `null` for:
   *   - jobs without a cursor (newly-queued, completed, failed)
   *   - cursors without `last_chapter_id` (chat-scope uses `last_pending_id`)
   *   - any book-service failure (graceful degrade)
   * JobDetailPanel renders the "Current chapter" section only when
   * this field is populated.
   *
   * /review-impl L6: during BE→FE rollout, pre-C6 knowledge-service
   * responses lack this field entirely. At runtime the property is
   * `undefined`, not `null` — nullish coalescing (`??`) handles both
   * identically, so consumers SHOULD use `job.current_chapter_title
   * ?? fallback` rather than direct access. The type is kept as
   * `string | null` (not `?: string | null`) to force tsc to flag
   * fixtures that forget the field; runtime consumers still tolerate
   * undefined via the `??` pattern.
   */
  current_chapter_title: string | null;
}

/**
 * C11 (D-K19b.1-01) — envelope for ``GET /extraction/jobs``. Paired
 * with ``next_cursor`` so the FE can advance to more history pages.
 * ``next_cursor`` is ``null`` on the last page.
 */
export interface ExtractionJobsPageResponse {
  items: ExtractionJobWire[];
  next_cursor: string | null;
}

export interface GraphStatsResponse {
  project_id: string;
  entity_count: number;
  fact_count: number;
  event_count: number;
  passage_count: number;
  /** ISO-8601 UTC, or null if never extracted. */
  last_extracted_at: string | null;
}

export type { CostEstimate } from './types/projectState';

// K19a.5 — /extraction/estimate payload. Mirrors EstimateRequest in
// services/knowledge-service/app/routers/public/extraction.py. BE does
// NOT take embedding_model or max_spend_usd on estimate — keep the
// contract narrow so a future `extra="forbid"` on BE wouldn't reject us.
export interface EstimateExtractionPayload {
  scope: ExtractionJobScopeWire;
  scope_range?: { chapter_range: [number, number] };
  llm_model: string;
}

// Mirrors StartJobRequest in
// services/knowledge-service/app/routers/public/extraction.py — BOTH
// llm_model and embedding_model are required by the BE; omitting either
// returns 422. Callers must have a prior job or a user-selected model.
export interface ExtractionStartPayload {
  scope: ExtractionJobScopeWire;
  scope_range?: { chapter_range: [number, number] };
  llm_model: string;
  embedding_model: string;
  max_spend_usd?: string;
  items_total?: number;
}

// Mirrors RebuildRequest (no `scope` field — handler hard-codes scope=all).
export interface RebuildPayload {
  llm_model: string;
  embedding_model: string;
  max_spend_usd?: string;
}

// K19a.6 — discriminated return type for PUT /embedding-model.
// Without `?confirm=true` the BE returns a warning preview; with it
// the destructive change runs and the BE returns the result metadata.
// The same-model path returns a third `{message, current_model}` shape
// which we fold into the warning variant's unknown fields.
export interface ChangeEmbeddingModelWarning {
  warning: string;
  current_model: string;
  new_model: string;
  action_required: 'confirm';
}
export interface ChangeEmbeddingModelNoop {
  message: string;
  current_model: string;
}
export interface ChangeEmbeddingModelResult {
  project_id: string;
  previous_model: string;
  new_model: string;
  nodes_deleted: number;
  extraction_status: 'disabled';
}
export type ChangeEmbeddingModelResponse =
  | ChangeEmbeddingModelWarning
  | ChangeEmbeddingModelNoop
  | ChangeEmbeddingModelResult;

// K19c.4 — user-scope entity (from the Track 2 Neo4j graph, projected
// into the shape returned by /v1/knowledge/me/entities). Mirrors
// services/knowledge-service/app/db/neo4j_repos/entities.py::Entity.
export interface Entity {
  id: string;
  user_id: string;
  project_id: string | null;
  name: string;
  canonical_name: string;
  kind: string;
  aliases: string[];
  canonical_version: number;
  source_types: string[];
  confidence: number;
  glossary_entity_id: string | null;
  anchor_score: number;
  archived_at: string | null;
  archive_reason: string | null;
  evidence_count: number;
  mention_count: number;
  /** K19d γ-a: set to true by PATCH /entities/{id}; gates the Unlock
   *  CTA in the detail panel. Extractions no longer re-append removed
   *  aliases until the user explicitly unlocks. */
  user_edited: boolean;
  /** C9 (D-K19d-γa-01): optimistic-concurrency counter. The FE sends
   *  this back via ``If-Match: W/"<version>"`` on PATCH. Bumped by
   *  every user-facing write on the BE. */
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface UserEntitiesResponse {
  entities: Entity[];
}

// K19b.8 — job logs. Cursor = log_id; page is full when
// len(logs) === limit, in which case next_cursor = max(log_id) and
// callers refetch with since_log_id = next_cursor. `null` cursor
// signals end-of-stream.
export type JobLogLevel = 'info' | 'warning' | 'error';

export interface JobLog {
  log_id: number;
  job_id: string;
  user_id: string;
  level: JobLogLevel;
  message: string;
  context: Record<string, unknown>;
  created_at: string;
}

export interface JobLogsResponse {
  logs: JobLog[];
  next_cursor: number | null;
}

// K19b.6 — GET /v1/knowledge/costs response shape. Decimal fields land
// as JSON strings; callers cast via Number() for display arithmetic.
// `monthly_budget_usd` and `monthly_remaining_usd` are null when the
// user hasn't set a user-wide cap via PUT /me/budget.
export interface UserCostSummary {
  all_time_usd: string;
  current_month_usd: string;
  monthly_budget_usd: string | null;
  monthly_remaining_usd: string | null;
}

// K19b.6 — PUT /v1/knowledge/me/budget body + response.
export interface SetUserBudgetPayload {
  ai_monthly_budget_usd: string | null;
}
export interface SetUserBudgetResponse {
  user_id: string;
  ai_monthly_budget_usd: string | null;
}

// K19a.6 — POST /extraction/disable response. Non-destructive flip
// of extraction_enabled=false while preserving Neo4j graph data.
export interface DisableExtractionResponse {
  project_id: string;
  extraction_status: string;
  graph_preserved: boolean;
  /** Set on the idempotent no-op path ("already disabled"). */
  message?: string;
}

// K19a.6 review-impl F3 — DELETE /extraction/graph returns a 200 body
// with the delete summary, not 204. Prior FE type was `Promise<void>`
// which drops the body silently. No caller currently reads these
// fields, but typing them keeps the FE↔BE contract honest and makes
// "how many nodes did we delete?" one TS inference away.
export interface DeleteGraphResponse {
  project_id: string;
  nodes_deleted: number;
  extraction_status: 'disabled';
}

// ── K20α — summary regeneration ────────────────────────────────────────

export interface RegenerateRequest {
  model_source: 'user_model' | 'platform_model';
  model_ref: string;
}

/**
 * K20α wire type for POST /v1/knowledge/me/summary/regenerate. Only
 * the 200-status subset shows up here; 409 (`user_edit_lock` /
 * `regen_concurrent_edit`) and 422 (`regen_guardrail_failed`) come
 * through as structured `detail.error_code` bodies that the hook
 * inspects — see `useRegenerateBio`.
 */
export type RegenerateStatus =
  | 'regenerated'
  | 'no_op_similarity'
  | 'no_op_empty_source';

export interface RegenerateResponse {
  status: RegenerateStatus;
  summary: Summary | null;
  skipped_reason: string | null;
}

// ── K19d.2 / K19d.4 — entities browse + detail ────────────────────────

export interface EntitiesListParams {
  project_id?: string;
  kind?: string;
  /** FE enforces min length 2 (matches BE Query min_length=2) so
   *  filter-free short keystrokes don't round-trip to a 422. */
  search?: string;
  limit?: number;
  offset?: number;
}

export interface EntitiesBrowseResponse {
  entities: Entity[];
  total: number;
}

/**
 * K19d.4 EntityRelation wire shape. Mirrors the Relation Pydantic
 * projection on the BE: a :RELATES_TO edge with the two endpoint
 * names + kinds included so the detail panel can render
 * `(subject)-[predicate]->(object)` without a second round-trip.
 */
export interface EntityRelation {
  id: string;
  subject_id: string;
  object_id: string;
  predicate: string;
  confidence: number;
  source_event_ids: string[];
  source_chapter: string | null;
  valid_from: string | null;
  valid_until: string | null;
  pending_validation: boolean;
  created_at: string | null;
  updated_at: string | null;
  subject_name: string | null;
  subject_kind: string | null;
  object_name: string | null;
  object_kind: string | null;
}

export interface EntityDetail {
  entity: Entity;
  relations: EntityRelation[];
  relations_truncated: boolean;
  total_relations: number;
}

// ── K19d γ-a — PATCH /entities/{id} body ──────────────────────────────

export interface EntityUpdatePayload {
  name?: string;
  kind?: string;
  /** Replaces the full list; not an append. Pass [] to clear. */
  aliases?: string[];
}

// ── K19d γ-b — POST /entities/{id}/merge-into/{other} ────────────────

export interface EntityMergeResponse {
  target: Entity;
}

export type EntityMergeErrorCode =
  | 'same_entity'
  | 'entity_not_found'
  | 'entity_archived'
  | 'glossary_conflict'
  | 'unknown';

// ── K19e.2 — Timeline list ────────────────────────────────────────────

/**
 * K19e.2 — timeline event. Mirrors
 * services/knowledge-service/app/db/neo4j_repos/events.py::Event
 * one-to-one so a future BE field addition surfaces here without
 * breaking the union. Fields not yet rendered by the FE (chronological
 * _order, archived_at) are retained in the type so downstream cycles
 * can start using them without a fresh api.ts PR.
 */
export interface TimelineEvent {
  id: string;
  user_id: string;
  project_id: string | null;
  title: string;
  canonical_title: string;
  summary: string | null;
  chapter_id: string | null;
  /**
   * C6 (D-K19e-β-01) — resolved chapter title denormalized in by
   * knowledge-service at response time via BookClient. Format:
   * `"Chapter N — Title"` (or `"Chapter N"` when the chapter has no
   * title set). `null` when the chapter isn't in book-service's
   * active set OR when book-service was unavailable — TimelineEventRow
   * falls back to the UUID-suffix short via `chapterShort()`.
   *
   * /review-impl L6: see `ExtractionJobWire.current_chapter_title`
   * for the rollout-window undefined-vs-null nuance. Same pattern
   * applies here — always consume via `event.chapter_title ??
   * fallback`.
   */
  chapter_title: string | null;
  event_order: number | null;
  chronological_order: number | null;
  participants: string[];
  confidence: number;
  source_types: string[];
  evidence_count: number;
  mention_count: number;
  archived_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface TimelineListParams {
  project_id?: string;
  /** Strict `event_order > after_order`. BE defers wall-clock date
   *  range (D-K19e-α-02) so narrative order is the only axis for MVP. */
  after_order?: number;
  before_order?: number;
  /** C10 (D-K19e-α-03): strict `chronological_order > after_chronological`.
   *  NULL-chrono events are excluded when either bound is set. */
  after_chronological?: number;
  before_chronological?: number;
  /** C10 (D-K19e-α-01): filter to events whose `participants` array
   *  contains the entity's display name, canonical_name, or any
   *  alias. BE resolves the id → participant-candidate list; cross-
   *  user / missing entity collapses to an empty timeline (no 404
   *  existence leak per KSA §6.4). */
  entity_id?: string;
  limit?: number;
  offset?: number;
}

export interface TimelineResponse {
  events: TimelineEvent[];
  total: number;
}

// ── K19e.5 — Drawer (passage) search ──────────────────────────────────

/**
 * K19e.5 — drawer search hit. Mirrors
 * services/knowledge-service/app/routers/public/drawers.py::DrawerSearchHit
 * (which drops ``user_id`` and the stored embedding from the public
 * wire). ``raw_score`` is cosine similarity in the [0, 1] practical
 * range — the card clamps to [0, 100]% for display.
 */
export interface DrawerSearchHit {
  id: string;
  project_id: string | null;
  source_type: string;
  source_id: string;
  chunk_index: number;
  text: string;
  is_hub: boolean;
  chapter_index: number | null;
  created_at: string | null;
  raw_score: number;
}

/** C8 (D-K19e-γa-01): closed enum mirrored from the BE's
 *  ``Literal['chapter','chat','glossary']``. Source of truth for the
 *  FE is this tuple — ``DrawerSourceType`` is derived from it, and
 *  consumers (filter pill row, pad helpers) iterate the tuple instead
 *  of hardcoding the 3-key set. Extending with a 4th type is a single
 *  edit here; BE Literal must be bumped in lockstep. */
export const DRAWER_SOURCE_TYPES = ['chapter', 'chat', 'glossary'] as const;
export type DrawerSourceType = (typeof DRAWER_SOURCE_TYPES)[number];

export interface DrawerSearchParams {
  project_id: string;
  query: string;
  limit?: number;
  /** C8: optional filter. Omit for "Any". */
  source_type?: DrawerSourceType;
}

export interface DrawerSearchResponse {
  hits: DrawerSearchHit[];
  /** ``null`` when the project has no embedding model configured
   *  (not-indexed-yet branch). ``string`` on any other outcome,
   *  including zero-hit live searches. */
  embedding_model: string | null;
  /** C8 (D-K19e-γa-01): facet counts per source_type. Always includes
   *  every key in the ``DrawerSourceType`` set (0 when absent) so the
   *  FE pill row stays layout-stable. Reflects project-wide totals
   *  filtered to the project's current embedding_model. */
  source_type_counts: Record<string, number>;
}

export type DrawerSearchErrorCode =
  | 'provider_error'
  | 'embedding_dim_mismatch'
  | 'unknown';

export interface DrawerSearchError extends Error {
  status?: number;
  errorCode: DrawerSearchErrorCode;
  /** BE forwards the provider's retryable hint on EmbeddingError so
   *  the FE can choose "Retry" vs "Fix config" messaging. Defaults
   *  to false when missing. */
  retryable: boolean;
  /** Server-supplied human-readable message if present. */
  detailMessage?: string;
}

/** Extract ``{error_code, message, retryable}`` from FastAPI's
 *  ``detail: {...}`` envelope. Consumers should ``switch`` on
 *  ``errorCode`` against the closed ``DrawerSearchErrorCode`` union. */
export function parseDrawersError(err: unknown): DrawerSearchError {
  const e = err as {
    message?: string;
    status?: number;
    body?: {
      detail?: {
        error_code?: string;
        message?: string;
        retryable?: boolean;
      };
    };
  };
  const detail = e.body?.detail;
  const code = (detail?.error_code ?? 'unknown') as DrawerSearchErrorCode;
  return Object.assign(new Error(e.message || 'drawer search failed'), {
    status: e.status,
    errorCode: code,
    retryable: Boolean(detail?.retryable ?? false),
    detailMessage: detail?.message,
  });
}

const BASE = '/v1/knowledge';

// D-K8-03: weak ETag format used by the knowledge-service routes.
const ifMatch = (version: number): Record<string, string> => ({
  'If-Match': `W/"${version}"`,
});

/**
 * D-K8-03: type-guarded helper for catching 412 Precondition Failed
 * errors from PATCH calls. The backend returns the CURRENT row in
 * the 412 body so callers can refresh their baseline in one
 * round-trip — no second GET needed.
 *
 * Usage:
 *   try { await knowledgeApi.updateProject(...) }
 *   catch (err) {
 *     if (isVersionConflict<Project>(err)) {
 *       // err.current is the fresh Project — update state and retry.
 *     }
 *   }
 */
export function isVersionConflict<T>(
  err: unknown,
): err is Error & { status: 412; current: T } {
  if (!(err instanceof Error)) return false;
  const e = err as Error & { status?: number; body?: unknown };
  if (e.status !== 412) return false;
  if (e.body == null || typeof e.body !== 'object') return false;
  // Attach `current` once for convenience — idempotent.
  (e as unknown as { current: T }).current = e.body as T;
  return true;
}

// Mirrors the helper in src/api.ts — needed for raw `fetch()` calls
// (the export endpoint streams a file and can't go through apiJson).
// Keeping this local matches the pattern in src/features/books/api.ts.
const apiBase = () => (import.meta.env.VITE_API_BASE as string | undefined) || '';

export const knowledgeApi = {
  // ── projects ───────────────────────────────────────────────────────────

  listProjects(
    params: ProjectListParams,
    token: string,
  ): Promise<ProjectListResponse> {
    const qs = new URLSearchParams();
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.cursor) qs.set('cursor', params.cursor);
    if (params.include_archived) qs.set('include_archived', 'true');
    const q = qs.toString();
    return apiJson<ProjectListResponse>(
      `${BASE}/projects${q ? `?${q}` : ''}`,
      { token },
    );
  },

  getProject(projectId: string, token: string): Promise<Project> {
    return apiJson<Project>(`${BASE}/projects/${projectId}`, { token });
  },

  createProject(
    payload: ProjectCreatePayload,
    token: string,
  ): Promise<Project> {
    return apiJson<Project>(`${BASE}/projects`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  updateProject(
    projectId: string,
    payload: ProjectUpdatePayload,
    token: string,
    expectedVersion: number,
  ): Promise<Project> {
    // D-K8-03: If-Match is strictly required for PATCH. The backend
    // returns 428 if the header is missing, 412 if it's stale.
    return apiJson<Project>(`${BASE}/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      token,
      headers: ifMatch(expectedVersion),
    });
  },

  archiveProject(projectId: string, token: string): Promise<Project> {
    return apiJson<Project>(`${BASE}/projects/${projectId}/archive`, {
      method: 'POST',
      token,
    });
  },

  deleteProject(projectId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/projects/${projectId}`, {
      method: 'DELETE',
      token,
    });
  },

  // ── summaries ──────────────────────────────────────────────────────────

  listSummaries(token: string): Promise<SummariesListResponse> {
    return apiJson<SummariesListResponse>(`${BASE}/summaries`, { token });
  },

  updateGlobalSummary(
    payload: SummaryUpdatePayload,
    token: string,
    expectedVersion: number | null,
  ): Promise<Summary> {
    // D-K8-03: If-Match is required for update path. null means
    // "first save" — no prior row, so no version to match. The
    // backend allows it; subsequent saves must send a version.
    return apiJson<Summary>(`${BASE}/summaries/global`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      token,
      headers: expectedVersion != null ? ifMatch(expectedVersion) : undefined,
    });
  },

  updateProjectSummary(
    projectId: string,
    payload: SummaryUpdatePayload,
    token: string,
    expectedVersion: number | null,
  ): Promise<Summary> {
    return apiJson<Summary>(`${BASE}/projects/${projectId}/summary`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      token,
      headers: expectedVersion != null ? ifMatch(expectedVersion) : undefined,
    });
  },

  // ── D-K8-01: global summary version history ────────────────────────────

  listGlobalSummaryVersions(
    token: string,
    limit = 50,
  ): Promise<SummaryVersionListResponse> {
    return apiJson<SummaryVersionListResponse>(
      `${BASE}/summaries/global/versions?limit=${limit}`,
      { token },
    );
  },

  getGlobalSummaryVersion(
    version: number,
    token: string,
  ): Promise<SummaryVersion> {
    return apiJson<SummaryVersion>(
      `${BASE}/summaries/global/versions/${version}`,
      { token },
    );
  },

  rollbackGlobalSummary(
    version: number,
    token: string,
    expectedVersion: number,
  ): Promise<Summary> {
    return apiJson<Summary>(
      `${BASE}/summaries/global/versions/${version}/rollback`,
      {
        method: 'POST',
        token,
        headers: ifMatch(expectedVersion),
      },
    );
  },

  // ── user data (GDPR) ───────────────────────────────────────────────────

  // The /export endpoint returns JSON with a Content-Disposition
  // attachment header. We fetch it directly (not apiJson) so the
  // browser can trigger the download via Blob + object URL.
  async exportUserData(token: string): Promise<{ blob: Blob; filename: string }> {
    const res = await fetch(`${apiBase()}${BASE}/user-data/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw Object.assign(new Error(text || res.statusText), {
        status: res.status,
      });
    }
    const blob = await res.blob();
    // Parse filename from Content-Disposition; fall back to a default.
    const disp = res.headers.get('Content-Disposition') ?? '';
    const match = /filename="([^"]+)"/.exec(disp);
    const filename = match?.[1] ?? 'loreweave-knowledge-export.json';
    return { blob, filename };
  },

  deleteAllUserData(token: string): Promise<UserDataDeleteResponse> {
    return apiJson<UserDataDeleteResponse>(`${BASE}/user-data`, {
      method: 'DELETE',
      token,
    });
  },

  // ── T2-close-1b-FE — K17.9 benchmark status ─────────────────────────
  /**
   * Fetch the latest K17.9 benchmark run for a project, optionally
   * scoped to a specific embedding model. Returns `has_run=false`
   * (200) when nothing has been benchmarked yet — not a 404, so the
   * FE can render a neutral "Run benchmark" badge instead of an error.
   *
   * Errors (404 = cross-user / nonexistent project) are thrown via
   * apiJson so the caller can choose to degrade silently (show no
   * badge) rather than alarming the user over a transient ownership
   * issue.
   */
  getBenchmarkStatus(
    projectId: string,
    embeddingModel: string | null,
    token: string,
  ): Promise<BenchmarkStatus> {
    const qs = new URLSearchParams();
    if (embeddingModel) qs.set('embedding_model', embeddingModel);
    const q = qs.toString();
    return apiJson<BenchmarkStatus>(
      `${BASE}/projects/${projectId}/benchmark-status${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── K19a.4 — extraction lifecycle ───────────────────────────────────────

  listExtractionJobs(projectId: string, token: string): Promise<ExtractionJobWire[]> {
    return apiJson<ExtractionJobWire[]>(
      `${BASE}/projects/${projectId}/extraction/jobs`,
      { token },
    );
  },

  // K19b.1 + C11 — user-scoped cross-project list, grouped by status,
  // with cursor pagination.
  // Powers the Jobs tab (no per-project fanout). BE validates
  // status_group (422 on missing/invalid), clamps limit to [1, 200],
  // and returns 422 on a malformed cursor.
  listAllJobs(
    params: {
      statusGroup: 'active' | 'history';
      limit?: number;
      cursor?: string;
    },
    token: string,
  ): Promise<ExtractionJobsPageResponse> {
    const qs = new URLSearchParams({ status_group: params.statusGroup });
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.cursor != null) qs.set('cursor', params.cursor);
    return apiJson<ExtractionJobsPageResponse>(
      `${BASE}/extraction/jobs?${qs.toString()}`,
      { token },
    );
  },

  getGraphStats(projectId: string, token: string): Promise<GraphStatsResponse> {
    return apiJson<GraphStatsResponse>(
      `${BASE}/projects/${projectId}/graph-stats`,
      { token },
    );
  },

  estimateExtraction(
    projectId: string,
    payload: EstimateExtractionPayload,
    token: string,
  ): Promise<CostEstimate> {
    return apiJson<CostEstimate>(
      `${BASE}/projects/${projectId}/extraction/estimate`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  startExtraction(
    projectId: string,
    payload: ExtractionStartPayload,
    token: string,
  ): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/projects/${projectId}/extraction/start`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  pauseExtraction(projectId: string, token: string): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/projects/${projectId}/extraction/pause`,
      { method: 'POST', token },
    );
  },

  resumeExtraction(projectId: string, token: string): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/projects/${projectId}/extraction/resume`,
      { method: 'POST', token },
    );
  },

  cancelExtraction(projectId: string, token: string): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/projects/${projectId}/extraction/cancel`,
      { method: 'POST', token },
    );
  },

  deleteGraph(projectId: string, token: string): Promise<DeleteGraphResponse> {
    return apiJson<DeleteGraphResponse>(
      `${BASE}/projects/${projectId}/extraction/graph`,
      { method: 'DELETE', token },
    );
  },

  rebuildGraph(
    projectId: string,
    payload: RebuildPayload,
    token: string,
  ): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/projects/${projectId}/extraction/rebuild`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  // K19a.6 — PUT /embedding-model. The BE requires `?confirm=true` for
  // the destructive path (deletes graph + switches model + disables).
  // Without `confirm`, BE returns a warning preview with
  // `action_required: 'confirm'`. Callers typically invoke twice: once
  // to preview (or skip that and go straight to confirm), once to
  // commit. Same-model requests return a third no-op shape.
  //
  // Prior signature returned Promise<Project> which was always wrong —
  // BE never returns a Project from this endpoint. K19a.5 callers
  // weren't calling this; K19a.6 dialog is the first real consumer.
  updateEmbeddingModel(
    projectId: string,
    embeddingModel: string,
    token: string,
    opts?: { confirm?: boolean },
  ): Promise<ChangeEmbeddingModelResponse> {
    const qs = opts?.confirm ? '?confirm=true' : '';
    return apiJson<ChangeEmbeddingModelResponse>(
      `${BASE}/projects/${projectId}/embedding-model${qs}`,
      {
        method: 'PUT',
        body: JSON.stringify({ embedding_model: embeddingModel }),
        token,
      },
    );
  },

  // ── K19c.4 — user-scope entities ───────────────────────────────────────

  listMyEntities(
    params: { scope: 'global'; limit?: number },
    token: string,
  ): Promise<UserEntitiesResponse> {
    const qs = new URLSearchParams({ scope: params.scope });
    if (params.limit != null) qs.set('limit', String(params.limit));
    return apiJson<UserEntitiesResponse>(
      `${BASE}/me/entities?${qs.toString()}`,
      { token },
    );
  },

  archiveMyEntity(entityId: string, token: string): Promise<void> {
    // BE returns 204 No Content on success; apiJson handles empty-body
    // responses by resolving with `undefined`.
    return apiJson<void>(`${BASE}/me/entities/${entityId}`, {
      method: 'DELETE',
      token,
    });
  },

  // ── K19b.8 — extraction job logs ───────────────────────────────────────

  listJobLogs(
    jobId: string,
    params: { sinceLogId?: number; limit?: number },
    token: string,
  ): Promise<JobLogsResponse> {
    const qs = new URLSearchParams();
    if (params.sinceLogId != null) qs.set('since_log_id', String(params.sinceLogId));
    if (params.limit != null) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return apiJson<JobLogsResponse>(
      `${BASE}/extraction/jobs/${jobId}/logs${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── K19b.6 — user-wide costs & budget ──────────────────────────────────

  getUserCosts(token: string): Promise<UserCostSummary> {
    return apiJson<UserCostSummary>(`${BASE}/costs`, { token });
  },

  setUserBudget(
    payload: SetUserBudgetPayload,
    token: string,
  ): Promise<SetUserBudgetResponse> {
    return apiJson<SetUserBudgetResponse>(`${BASE}/me/budget`, {
      method: 'PUT',
      body: JSON.stringify(payload),
      token,
    });
  },

  // K19a.6 — non-destructive POST /extraction/disable. Preserves the
  // Neo4j graph; contrasts with deleteGraph (destructive) and
  // updateEmbeddingModel (destructive).
  disableExtraction(
    projectId: string,
    token: string,
  ): Promise<DisableExtractionResponse> {
    return apiJson<DisableExtractionResponse>(
      `${BASE}/projects/${projectId}/extraction/disable`,
      { method: 'POST', token },
    );
  },

  // ── K20α — summary regeneration ───────────────────────────────────────

  regenerateGlobalBio(
    body: RegenerateRequest,
    token: string,
  ): Promise<RegenerateResponse> {
    return apiJson<RegenerateResponse>(`${BASE}/me/summary/regenerate`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  // ── K19d — entities browse + detail ──────────────────────────────────

  listEntities(
    params: EntitiesListParams,
    token: string,
  ): Promise<EntitiesBrowseResponse> {
    const qs = new URLSearchParams();
    if (params.project_id != null) qs.set('project_id', params.project_id);
    if (params.kind != null) qs.set('kind', params.kind);
    if (params.search != null) qs.set('search', params.search);
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.offset != null) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson<EntitiesBrowseResponse>(
      `${BASE}/entities${q ? `?${q}` : ''}`,
      { token },
    );
  },

  getEntityDetail(entityId: string, token: string): Promise<EntityDetail> {
    return apiJson<EntityDetail>(
      `${BASE}/entities/${encodeURIComponent(entityId)}`,
      { token },
    );
  },

  // ── K19d γ-a — PATCH /entities/{id} ──────────────────────────────────

  updateEntity(
    entityId: string,
    body: EntityUpdatePayload,
    ifMatchVersion: number,
    token: string,
  ): Promise<Entity> {
    return apiJson<Entity>(
      `${BASE}/entities/${encodeURIComponent(entityId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
        token,
        // C9 (D-K19d-γa-01): strict If-Match — BE 428s without it.
        headers: ifMatch(ifMatchVersion),
      },
    );
  },

  // C9 (D-K19d-γa-02) — POST /entities/{id}/unlock
  unlockEntity(entityId: string, token: string): Promise<Entity> {
    return apiJson<Entity>(
      `${BASE}/entities/${encodeURIComponent(entityId)}/unlock`,
      {
        method: 'POST',
        token,
      },
    );
  },

  // ── K19d γ-b — POST /entities/{id}/merge-into/{other} ────────────────

  mergeEntityInto(
    sourceId: string,
    targetId: string,
    token: string,
  ): Promise<EntityMergeResponse> {
    return apiJson<EntityMergeResponse>(
      `${BASE}/entities/${encodeURIComponent(sourceId)}/merge-into/${encodeURIComponent(targetId)}`,
      {
        method: 'POST',
        token,
      },
    );
  },

  // ── K19e.2 — GET /v1/knowledge/timeline ──────────────────────────────

  listTimeline(
    params: TimelineListParams,
    token: string,
  ): Promise<TimelineResponse> {
    const qs = new URLSearchParams();
    if (params.project_id != null) qs.set('project_id', params.project_id);
    if (params.after_order != null)
      qs.set('after_order', String(params.after_order));
    if (params.before_order != null)
      qs.set('before_order', String(params.before_order));
    if (params.after_chronological != null)
      qs.set('after_chronological', String(params.after_chronological));
    if (params.before_chronological != null)
      qs.set('before_chronological', String(params.before_chronological));
    if (params.entity_id != null) qs.set('entity_id', params.entity_id);
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.offset != null) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson<TimelineResponse>(
      `${BASE}/timeline${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── K19e.5 — GET /v1/knowledge/drawers/search ────────────────────────

  searchDrawers(
    params: DrawerSearchParams,
    token: string,
  ): Promise<DrawerSearchResponse> {
    const qs = new URLSearchParams();
    qs.set('project_id', params.project_id);
    qs.set('query', params.query);
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.source_type != null) qs.set('source_type', params.source_type);
    return apiJson<DrawerSearchResponse>(
      `${BASE}/drawers/search?${qs.toString()}`,
      { token },
    );
  },
};

// Re-exported for consumers that need them alongside the wire types.
export type { ExtractionJobStatus };
