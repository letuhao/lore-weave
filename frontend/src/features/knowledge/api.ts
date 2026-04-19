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

  getGraphStats(projectId: string, token: string): Promise<GraphStatsResponse> {
    return apiJson<GraphStatsResponse>(
      `${BASE}/projects/${projectId}/graph-stats`,
      { token },
    );
  },

  estimateExtraction(
    projectId: string,
    payload: ExtractionStartPayload,
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

  deleteGraph(projectId: string, token: string): Promise<void> {
    return apiJson<void>(
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

  updateEmbeddingModel(
    projectId: string,
    embeddingModel: string,
    token: string,
  ): Promise<Project> {
    return apiJson<Project>(
      `${BASE}/projects/${projectId}/embedding-model`,
      {
        method: 'PUT',
        body: JSON.stringify({ embedding_model: embeddingModel }),
        token,
      },
    );
  },
};

// Re-exported for consumers that need them alongside the wire types.
export type { ExtractionJobStatus };
