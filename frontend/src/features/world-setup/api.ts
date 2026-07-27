// World Setup — gateway calls for the glossary-build pipeline. Relative /v1 rides
// the Vite proxy → gateway (dev :3123) / nginx (prod), same `apiJson` + token
// convention as the other composition features.
import { apiJson } from '@/api';

import type { BuildEdge, BuildRun, CreateRunBody, WorklistItem } from './types';

const BASE = '/v1/composition/glossary-build';

export const worldSetupApi = {
  createRun(body: CreateRunBody, token: string): Promise<BuildRun> {
    return apiJson<BuildRun>(`${BASE}/runs`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  /** draft → plan_ready. One bounded planner call; enumerate-only (no detail). */
  plan(runId: string, token: string): Promise<BuildRun> {
    return apiJson<BuildRun>(`${BASE}/runs/${runId}/plan`, { method: 'POST', token });
  },
  /** [checkpoint 1] Approve — optionally the human's TRIMMED worklist. */
  approvePlan(runId: string, worklist: WorklistItem[] | null, token: string): Promise<BuildRun> {
    return apiJson<BuildRun>(`${BASE}/runs/${runId}/approve-plan`, {
      method: 'POST', body: JSON.stringify({ worklist }), token,
    });
  },
  get(runId: string, token: string): Promise<BuildRun> {
    return apiJson<BuildRun>(`${BASE}/runs/${runId}`, { token });
  },
  list(bookId: string, token: string): Promise<{ items: BuildRun[] }> {
    return apiJson<{ items: BuildRun[] }>(
      `${BASE}/runs?book_id=${encodeURIComponent(bookId)}`, { token },
    );
  },
  /** [after checkpoint 2] project nodes + resolve relation NAMES → graph ids. */
  projectKg(runId: string, token: string): Promise<BuildRun> {
    return apiJson<BuildRun>(`${BASE}/runs/${runId}/project-kg`, { method: 'POST', token });
  },
  /** [checkpoint 3] write the approved, resolved edges. */
  approveEdges(runId: string, edges: BuildEdge[] | null, token: string): Promise<BuildRun> {
    return apiJson<BuildRun>(`${BASE}/runs/${runId}/approve-edges`, {
      method: 'POST', body: JSON.stringify({ edges }), token,
    });
  },
  cancel(runId: string, token: string): Promise<BuildRun> {
    return apiJson<BuildRun>(`${BASE}/runs/${runId}/cancel`, { method: 'POST', token });
  },
};
