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
  ): Promise<Project> {
    return apiJson<Project>(`${BASE}/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      token,
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
  ): Promise<Summary> {
    return apiJson<Summary>(`${BASE}/summaries/global`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      token,
    });
  },

  updateProjectSummary(
    projectId: string,
    payload: SummaryUpdatePayload,
    token: string,
  ): Promise<Summary> {
    return apiJson<Summary>(`${BASE}/projects/${projectId}/summary`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      token,
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
