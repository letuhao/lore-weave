// D-BATCH-RESEARCH-JOB M3 — typed client for the async batch entity-research job.
// A job researches up to max_entities entities of one book kind on the web (one paid BYOK
// search per entity), attaching sourced 'reference' evidence. All calls go through the
// shared apiJson (JWT in `token`, relative /v1 proxied to the gateway).

import { apiJson } from '../../api';

export type ResearchJobStatus =
  | 'pending'
  | 'running'
  | 'paused_user'
  | 'complete'
  | 'failed'
  | 'cancelled';

export interface ResearchJob {
  job_id: string;
  book_id: string;
  kind_id: string;
  query_template: string;
  max_results: number;
  max_entities: number;
  est_cost_usd: string;
  status: ResearchJobStatus;
  items_total: number;
  items_processed: number;
  searches_run: number;
  sources_attached: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface ResearchEstimate {
  entity_count: number;
  planned_entities: number;
  est_cost_usd: string;
  per_search_usd: string;
  hard_cap: number;
  cost_is_indicative: boolean;
}

export interface CreateResearchJobReq {
  query_template: string;
  max_results: number;
  max_entities: number;
}

const BASE = '/v1/glossary';

/** A research-job status is terminal when no worker will touch it again. */
export const isTerminalResearchStatus = (s: ResearchJobStatus): boolean =>
  s === 'complete' || s === 'failed' || s === 'cancelled';

/** Active = the worker will (or is) processing it → the FE polls. */
export const isActiveResearchStatus = (s: ResearchJobStatus): boolean =>
  s === 'pending' || s === 'running';

export const researchApi = {
  estimate(bookId: string, kindId: string, maxEntities: number, token: string): Promise<ResearchEstimate> {
    const q = maxEntities > 0 ? `?max_entities=${maxEntities}` : '';
    return apiJson<ResearchEstimate>(`${BASE}/books/${bookId}/kinds/${kindId}/research-estimate${q}`, { token });
  },

  create(bookId: string, kindId: string, req: CreateResearchJobReq, token: string): Promise<ResearchJob> {
    return apiJson<ResearchJob>(`${BASE}/books/${bookId}/kinds/${kindId}/research-jobs`, {
      method: 'POST',
      body: JSON.stringify(req),
      token,
    });
  },

  list(bookId: string, token: string): Promise<ResearchJob[]> {
    return apiJson<{ jobs: ResearchJob[] }>(`${BASE}/books/${bookId}/research-jobs`, { token }).then((r) => r.jobs);
  },

  get(bookId: string, jobId: string, token: string): Promise<ResearchJob> {
    return apiJson<ResearchJob>(`${BASE}/books/${bookId}/research-jobs/${jobId}`, { token });
  },

  pause(bookId: string, jobId: string, token: string): Promise<ResearchJob> {
    return apiJson<ResearchJob>(`${BASE}/books/${bookId}/research-jobs/${jobId}/pause`, { method: 'POST', token });
  },
  resume(bookId: string, jobId: string, token: string): Promise<ResearchJob> {
    return apiJson<ResearchJob>(`${BASE}/books/${bookId}/research-jobs/${jobId}/resume`, { method: 'POST', token });
  },
  cancel(bookId: string, jobId: string, token: string): Promise<ResearchJob> {
    return apiJson<ResearchJob>(`${BASE}/books/${bookId}/research-jobs/${jobId}/cancel`, { method: 'POST', token });
  },
};
