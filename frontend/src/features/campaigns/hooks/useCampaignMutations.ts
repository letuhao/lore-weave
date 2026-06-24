import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { campaignsApi } from '../api';
import type {
  Campaign,
  CreateCampaignPayload,
  EstimateRequest,
  EstimateResponse,
  UpdateCampaignPayload,
} from '../types';

/** On-demand cost/time estimate for the wizard's review step. */
export function useEstimateCampaign(opts?: {
  onSuccess?: (r: EstimateResponse) => void;
  onError?: (err: Error) => void;
}) {
  const { accessToken } = useAuth();
  return useMutation({
    mutationFn: (req: EstimateRequest) => campaignsApi.estimate(req, accessToken!),
    onSuccess: opts?.onSuccess,
    onError: (err) => opts?.onError?.(err as Error),
  });
}

/** Launch = create then start (the wizard's final action). A failure at either
 *  step surfaces to onError; the create's 409 (embedding conflict / over-budget)
 *  is read by the caller via campaignErrorCode. */
export function useLaunchCampaign(opts?: {
  onSuccess?: (c: Campaign) => void;
  onError?: (err: Error) => void;
}) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CreateCampaignPayload) => {
      const created = await campaignsApi.create(payload, accessToken!);
      return campaignsApi.start(created.campaign_id, accessToken!);
    },
    onSuccess: async (c) => {
      await qc.invalidateQueries({ queryKey: ['campaigns'] });
      opts?.onSuccess?.(c);
    },
    onError: (err) => opts?.onError?.(err as Error),
  });
}

/** Cancel a campaign (the detail page's one control in S5c). */
export function useCancelCampaign(opts?: {
  onSuccess?: (c: Campaign) => void;
  onError?: (err: Error) => void;
}) {
  return useCampaignAction((id, token) => campaignsApi.cancel(id, token), opts);
}

// ── S6 monitor controls ──────────────────────────────────────────────────────

/** Shared shape for the single-arg (campaignId) lifecycle mutations; invalidates
 *  the campaign + its progress poll so the monitor reflects the new state at once. */
function useCampaignAction(
  fn: (id: string, token: string) => Promise<Campaign>,
  opts?: { onSuccess?: (c: Campaign) => void; onError?: (err: Error) => void },
) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (campaignId: string) => fn(campaignId, accessToken!),
    onSuccess: async (c) => {
      await qc.invalidateQueries({ queryKey: ['campaigns'] });
      await qc.invalidateQueries({ queryKey: ['campaigns', c.campaign_id] });
      await qc.invalidateQueries({ queryKey: ['campaign-progress', c.campaign_id] });
      opts?.onSuccess?.(c);
    },
    onError: (err) => opts?.onError?.(err as Error),
  });
}

export function usePauseCampaign(opts?: { onSuccess?: (c: Campaign) => void; onError?: (err: Error) => void }) {
  return useCampaignAction((id, token) => campaignsApi.pause(id, token), opts);
}

/** Resume = POST /start (paused → running); may 409 CAMPAIGN_OVER_BUDGET. */
export function useResumeCampaign(opts?: { onSuccess?: (c: Campaign) => void; onError?: (err: Error) => void }) {
  return useCampaignAction((id, token) => campaignsApi.start(id, token), opts);
}

/** G2 — re-run failed chapters (null = all failed). Re-arms to running; invalidates
 *  the campaign detail + progress + report so the monitor reflects it at once. */
export function useRerunFailed(opts?: { onSuccess?: (c: Campaign) => void; onError?: (err: Error) => void }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { campaignId: string; chapterIds?: string[] | null }) =>
      campaignsApi.rerunFailed(args.campaignId, args.chapterIds ?? null, accessToken!),
    onSuccess: async (c) => {
      await qc.invalidateQueries({ queryKey: ['campaigns', c.campaign_id] });
      await qc.invalidateQueries({ queryKey: ['campaign-progress', c.campaign_id] });
      await qc.invalidateQueries({ queryKey: ['campaign-report', c.campaign_id] });
      opts?.onSuccess?.(c);
    },
    onError: (err) => opts?.onError?.(err as Error),
  });
}

/** Raise/lower the budget cap (PATCH). Does NOT auto-resume a paused campaign. */
export function useUpdateBudget(opts?: { onSuccess?: (c: Campaign) => void; onError?: (err: Error) => void }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { campaignId: string; budgetUsd: string }) =>
      campaignsApi.updateBudget(args.campaignId, args.budgetUsd, accessToken!),
    onSuccess: async (c) => {
      await qc.invalidateQueries({ queryKey: ['campaigns', c.campaign_id] });
      await qc.invalidateQueries({ queryKey: ['campaign-progress', c.campaign_id] });
      opts?.onSuccess?.(c);
    },
    onError: (err) => opts?.onError?.(err as Error),
  });
}

/** D-FACTORY-SWITCH-MODEL-RESUME — partial PATCH (budget and/or the switchable
 *  models). Invalidates the campaign detail so the new picks render; the caller
 *  chains a resume on success. */
export function useUpdateCampaign(opts?: { onSuccess?: (c: Campaign) => void; onError?: (err: Error) => void }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { campaignId: string; patch: UpdateCampaignPayload }) =>
      campaignsApi.updateCampaign(args.campaignId, args.patch, accessToken!),
    onSuccess: async (c) => {
      await qc.invalidateQueries({ queryKey: ['campaigns', c.campaign_id] });
      await qc.invalidateQueries({ queryKey: ['campaign-progress', c.campaign_id] });
      opts?.onSuccess?.(c);
    },
    onError: (err) => opts?.onError?.(err as Error),
  });
}
