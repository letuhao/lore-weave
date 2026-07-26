// #20_agent_mode.md — gateway calls for the authoring-run REST surface
// (`/v1/composition/authoring-runs/*`). Relative /v1 rides the Vite proxy →
// gateway (dev) / nginx (prod), same `apiJson` client every other composition
// FE caller uses (compositionApi/planForgeApi precedent).
import { apiJson } from '@/api';
import type {
  AuthoringRun,
  AuthoringRunReport,
  CreateAuthoringRunBody,
  RejectUnitResult,
  RevertAllResult,
} from './types';

const BASE = '/v1/composition/authoring-runs';

/** The shape a 502 REVERT_ALL_PARTIAL (or any HTTPException(detail={...})) lands
 * in via apiJson's thrown error (`body.detail`). */
interface DetailedHttpError {
  status?: number;
  body?: { detail?: unknown };
  message?: string;
}

function errorDetail(e: unknown): string {
  const err = e as DetailedHttpError;
  const d = err.body?.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object' && 'detail' in (d as Record<string, unknown>)) {
    const inner = (d as Record<string, unknown>).detail;
    if (typeof inner === 'string') return inner;
  }
  return err.message || 'request failed';
}

export const authoringRunsApi = {
  list(bookId: string, token: string, limit = 20): Promise<{ items: AuthoringRun[] }> {
    return apiJson(`${BASE}?book_id=${encodeURIComponent(bookId)}&limit=${limit}`, { token });
  },
  get(runId: string, token: string): Promise<AuthoringRun> {
    return apiJson(`${BASE}/${runId}`, { token });
  },
  create(body: CreateAuthoringRunBody, token: string): Promise<AuthoringRun> {
    return apiJson(BASE, { method: 'POST', body: JSON.stringify(body), token });
  },
  gate(runId: string, token: string): Promise<AuthoringRun> {
    return apiJson(`${BASE}/${runId}/gate`, { method: 'POST', token });
  },
  start(runId: string, token: string): Promise<AuthoringRun> {
    return apiJson(`${BASE}/${runId}/start`, { method: 'POST', token });
  },
  pause(runId: string, token: string): Promise<AuthoringRun> {
    return apiJson(`${BASE}/${runId}/pause`, { method: 'POST', token });
  },
  resume(runId: string, token: string): Promise<AuthoringRun> {
    return apiJson(`${BASE}/${runId}/resume`, { method: 'POST', token });
  },
  close(runId: string, token: string): Promise<AuthoringRun> {
    return apiJson(`${BASE}/${runId}/close`, { method: 'POST', token });
  },
  // D4a mid-run toggle — new PATCH endpoint (spec §backend surface). Not yet
  // present on a not-updated server; the caller surfaces the resulting error.
  setPausePolicy(runId: string, pauseAfterEachUnit: boolean, token: string): Promise<AuthoringRun> {
    return apiJson(`${BASE}/${runId}/pause-policy`, {
      method: 'PATCH', body: JSON.stringify({ pause_after_each_unit: pauseAfterEachUnit }), token,
    });
  },
  report(runId: string, token: string): Promise<AuthoringRunReport> {
    return apiJson(`${BASE}/${runId}/report`, { token });
  },
  acceptUnit(runId: string, unitIndex: number, token: string) {
    return apiJson(`${BASE}/${runId}/units/${unitIndex}/accept`, { method: 'POST', token });
  },
  rejectUnit(runId: string, unitIndex: number, token: string): Promise<RejectUnitResult> {
    return apiJson(`${BASE}/${runId}/units/${unitIndex}/reject`, { method: 'POST', token });
  },
  // D9 — revert-all's partial-failure path is a NORMAL outcome (the service
  // documents it, the router just carries it over HTTP as a 502 so it's
  // distinguishable from "nothing happened"). Normalize both the 200 success
  // and the 502 partial-failure into the SAME RevertAllResult shape so callers
  // never need a special catch just to read which units reverted.
  async revertAll(runId: string, token: string): Promise<RevertAllResult> {
    try {
      return await apiJson<RevertAllResult>(`${BASE}/${runId}/revert-all`, { method: 'POST', token });
    } catch (e) {
      const err = e as DetailedHttpError;
      const detail = err.body?.detail as (RevertAllResult & { code?: string }) | undefined;
      if (err.status === 502 && detail?.code === 'REVERT_ALL_PARTIAL') {
        const { code: _code, ...result } = detail;
        return result;
      }
      throw e;
    }
  },
};

export { errorDetail };
