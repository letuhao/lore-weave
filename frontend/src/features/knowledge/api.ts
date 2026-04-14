import { apiJson } from '../../api';
import type {
  Project,
  ProjectCreatePayload,
  ProjectListParams,
  ProjectListResponse,
  ProjectUpdatePayload,
  SummariesListResponse,
  Summary,
  SummaryUpdatePayload,
  UserDataDeleteResponse,
} from './types';

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
};
