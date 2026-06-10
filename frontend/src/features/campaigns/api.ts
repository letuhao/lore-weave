import { apiJson } from '../../api';
import type {
  Campaign,
  CampaignDetail,
  CreateCampaignPayload,
  EstimateRequest,
  EstimateResponse,
} from './types';

// Gateway proxies /v1/campaigns/* generically (no per-route config). Relative
// paths ride the dev vite-proxy / prod nginx path (see ../../api.ts).
export const campaignsApi = {
  list(token: string): Promise<Campaign[]> {
    return apiJson<Campaign[]>('/v1/campaigns', { token });
  },

  get(campaignId: string, token: string): Promise<CampaignDetail> {
    return apiJson<CampaignDetail>(`/v1/campaigns/${campaignId}`, { token });
  },

  create(payload: CreateCampaignPayload, token: string): Promise<Campaign> {
    return apiJson<Campaign>('/v1/campaigns', {
      token, method: 'POST', body: JSON.stringify(payload),
    });
  },

  estimate(payload: EstimateRequest, token: string): Promise<EstimateResponse> {
    return apiJson<EstimateResponse>('/v1/campaigns/estimate', {
      token, method: 'POST', body: JSON.stringify(payload),
    });
  },

  start(campaignId: string, token: string): Promise<Campaign> {
    return apiJson<Campaign>(`/v1/campaigns/${campaignId}/start`, {
      token, method: 'POST',
    });
  },

  cancel(campaignId: string, token: string): Promise<Campaign> {
    return apiJson<Campaign>(`/v1/campaigns/${campaignId}/cancel`, {
      token, method: 'POST',
    });
  },
};

/** FastAPI nests the error code under `detail.code` (HTTPException(detail={code,…})).
 *  apiJson attaches the parsed body to the thrown error — read the code from there. */
export function campaignErrorCode(err: unknown): string | undefined {
  const body = (err as { body?: { detail?: { code?: string } } })?.body;
  return body?.detail?.code;
}
