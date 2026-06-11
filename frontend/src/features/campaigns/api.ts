import { apiJson } from '../../api';
import type {
  Campaign,
  CampaignDetail,
  CampaignProgress,
  CampaignReport,
  ChapterPage,
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

  pause(campaignId: string, token: string): Promise<Campaign> {
    return apiJson<Campaign>(`/v1/campaigns/${campaignId}/pause`, {
      token, method: 'POST',
    });
  },

  cancel(campaignId: string, token: string): Promise<Campaign> {
    return apiJson<Campaign>(`/v1/campaigns/${campaignId}/cancel`, {
      token, method: 'POST',
    });
  },

  // S6 — lightweight live-progress poll (per-stage counts, not the full chapters[]).
  progress(campaignId: string, token: string): Promise<CampaignProgress> {
    return apiJson<CampaignProgress>(`/v1/campaigns/${campaignId}/progress`, { token });
  },

  // G1 — completion / wake-up report (outcome + spend-vs-estimate + error groups).
  report(campaignId: string, token: string): Promise<CampaignReport> {
    return apiJson<CampaignReport>(`/v1/campaigns/${campaignId}/report`, { token });
  },

  // D-S6-CHAPTER-PAGING — one server-side page of the per-chapter projection.
  chapters(
    campaignId: string,
    opts: { status: 'attention' | 'all'; limit: number; offset: number },
    token: string,
  ): Promise<ChapterPage> {
    const q = `status=${opts.status}&limit=${opts.limit}&offset=${opts.offset}`;
    return apiJson<ChapterPage>(`/v1/campaigns/${campaignId}/chapters?${q}`, { token });
  },

  // G2 — re-run failed chapters (null/empty chapterIds = all failed). Re-arms the
  // campaign to running; the driver re-dispatches the reset stages.
  rerunFailed(campaignId: string, chapterIds: string[] | null, token: string): Promise<Campaign> {
    return apiJson<Campaign>(`/v1/campaigns/${campaignId}/rerun-failed`, {
      token, method: 'POST',
      body: JSON.stringify(chapterIds && chapterIds.length ? { chapter_ids: chapterIds } : {}),
    });
  },

  updateBudget(campaignId: string, budgetUsd: string, token: string): Promise<Campaign> {
    return apiJson<Campaign>(`/v1/campaigns/${campaignId}`, {
      token, method: 'PATCH', body: JSON.stringify({ budget_usd: budgetUsd }),
    });
  },
};

/** FastAPI nests the error code under `detail.code` (HTTPException(detail={code,…})).
 *  apiJson attaches the parsed body to the thrown error — read the code from there. */
export function campaignErrorCode(err: unknown): string | undefined {
  const body = (err as { body?: { detail?: { code?: string } } })?.body;
  return body?.detail?.code;
}
