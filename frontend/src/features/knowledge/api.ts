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

  // K19b.1 — user-scoped cross-project list, grouped by status.
  // Powers the Jobs tab (no per-project fanout). BE validates
  // status_group (422 on missing/invalid) and clamps limit to [1, 200].
  listAllJobs(
    params: { statusGroup: 'active' | 'history'; limit?: number },
    token: string,
  ): Promise<ExtractionJobWire[]> {
    const qs = new URLSearchParams({ status_group: params.statusGroup });
    if (params.limit != null) qs.set('limit', String(params.limit));
    return apiJson<ExtractionJobWire[]>(
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
};

// Re-exported for consumers that need them alongside the wire types.
export type { ExtractionJobStatus };
