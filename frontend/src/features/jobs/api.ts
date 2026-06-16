import { apiJson, apiBase } from '../../api';
import type {
  Job,
  JobListParams,
  JobListResponse,
  JobControlAction,
  JobSummary,
  JobFairness,
} from './types';

// Gateway proxies /v1/jobs/* generically to jobs-service. Relative paths ride the
// dev vite-proxy / prod nginx path (see ../../api.ts). The SSE stream is reached via
// a fetch-stream (NOT EventSource) because jobs-service requires the bearer in the
// Authorization header and rejects token-in-URL (it would leak into logs).
export const jobsApi = {
  list(params: JobListParams, token: string): Promise<JobListResponse> {
    const q = new URLSearchParams();
    if (params.status) q.set('status', params.status);
    if (params.kind) q.set('kind', params.kind);
    if (params.parent) q.set('parent', params.parent);
    if (params.q) q.set('q', params.q);
    if (params.bucket) q.set('bucket', params.bucket);
    if (params.cursor) q.set('cursor', params.cursor);
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.limit != null) q.set('limit', String(params.limit));
    const qs = q.toString();
    return apiJson<JobListResponse>(`/v1/jobs${qs ? `?${qs}` : ''}`, { token });
  },

  /** Owner-scoped status counts for the 4 summary cards. */
  summary(token: string): Promise<JobSummary> {
    return apiJson<JobSummary>('/v1/jobs/summary', { token });
  },

  /** P5 — owner-scoped fair-scheduling depth ("N queued behind your cap"). */
  fairness(token: string): Promise<JobFairness> {
    return apiJson<JobFairness>('/v1/jobs/fairness', { token });
  },

  get(service: string, jobId: string, token: string): Promise<Job> {
    return apiJson<Job>(`/v1/jobs/${encodeURIComponent(service)}/${encodeURIComponent(jobId)}`, {
      token,
    });
  },

  /** Cancel / pause / resume — routed to the owning service, which re-verifies ownership. */
  control(
    service: string,
    jobId: string,
    action: JobControlAction,
    token: string,
  ): Promise<Job> {
    return apiJson<Job>(
      `/v1/jobs/${encodeURIComponent(service)}/${encodeURIComponent(jobId)}/${action}`,
      { token, method: 'POST' },
    );
  },

  /** Absolute URL for the SSE fetch-stream. The bearer rides the Authorization header. */
  streamUrl(): string {
    return `${apiBase()}/v1/jobs/stream`;
  },
};
