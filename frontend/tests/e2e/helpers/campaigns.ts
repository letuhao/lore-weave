import type { APIRequestContext, APIResponse } from '@playwright/test';

// Auto-Draft Factory (campaign-service) API helpers for E2E.
// These return the RAW APIResponse so specs can assert status codes + error
// envelopes (the gap-fix routes are tested at the contract/guard layer through
// the gateway — the data-bearing happy-path is covered by the BE real-PG
// integration suites + the [MODEL] live scenarios). All routes are owner-scoped.

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

// A syntactically-valid UUID that no campaign will ever have — used to assert
// owner-scoped 404 on every route without seeding a campaign.
export const ABSENT_CAMPAIGN_ID = '00000000-0000-4000-8000-000000000000';

export const estimateCampaign = (r: APIRequestContext, token: string, body: unknown): Promise<APIResponse> =>
  r.post('/v1/campaigns/estimate', { ...auth(token), data: body });

export const createCampaign = (r: APIRequestContext, token: string, body: unknown): Promise<APIResponse> =>
  r.post('/v1/campaigns', { ...auth(token), data: body });

export const listCampaigns = (r: APIRequestContext, token: string): Promise<APIResponse> =>
  r.get('/v1/campaigns', auth(token));

export const getCampaign = (r: APIRequestContext, token: string, id: string): Promise<APIResponse> =>
  r.get(`/v1/campaigns/${id}`, auth(token));

export const getReport = (r: APIRequestContext, token: string, id: string): Promise<APIResponse> =>
  r.get(`/v1/campaigns/${id}/report`, auth(token));

export const getActivity = (r: APIRequestContext, token: string, id: string, q = ''): Promise<APIResponse> =>
  r.get(`/v1/campaigns/${id}/activity${q}`, auth(token));

export const getChapters = (r: APIRequestContext, token: string, id: string, q = ''): Promise<APIResponse> =>
  r.get(`/v1/campaigns/${id}/chapters${q}`, auth(token));

export const patchCampaign = (r: APIRequestContext, token: string, id: string, body: unknown): Promise<APIResponse> =>
  r.patch(`/v1/campaigns/${id}`, { ...auth(token), data: body });

export const startCampaign = (r: APIRequestContext, token: string, id: string): Promise<APIResponse> =>
  r.post(`/v1/campaigns/${id}/start`, auth(token));

export const pauseCampaign = (r: APIRequestContext, token: string, id: string): Promise<APIResponse> =>
  r.post(`/v1/campaigns/${id}/pause`, auth(token));

export const cancelCampaign = (r: APIRequestContext, token: string, id: string): Promise<APIResponse> =>
  r.post(`/v1/campaigns/${id}/cancel`, auth(token));

export const rerunFailed = (r: APIRequestContext, token: string, id: string, body?: unknown): Promise<APIResponse> =>
  r.post(`/v1/campaigns/${id}/rerun-failed`, { ...auth(token), ...(body ? { data: body } : {}) });

/** Read the JSON error envelope `{detail:{code,message}}` (campaign-service shape). */
export async function errorCode(resp: APIResponse): Promise<string | undefined> {
  try {
    const j = (await resp.json()) as { detail?: { code?: string } | string };
    return typeof j.detail === 'object' ? j.detail?.code : undefined;
  } catch {
    return undefined;
  }
}

/** True if the gateway can reach campaign-service (list returns 2xx). Specs skip
 * cleanly when the campaign-service isn't in the stack-up. */
export async function campaignServiceUp(r: APIRequestContext, token: string): Promise<boolean> {
  try {
    return (await listCampaigns(r, token)).ok();
  } catch {
    return false;
  }
}
