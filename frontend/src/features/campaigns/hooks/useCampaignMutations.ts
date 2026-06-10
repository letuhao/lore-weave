import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { campaignsApi } from '../api';
import type {
  Campaign,
  CreateCampaignPayload,
  EstimateRequest,
  EstimateResponse,
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
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (campaignId: string) => campaignsApi.cancel(campaignId, accessToken!),
    onSuccess: async (c) => {
      await qc.invalidateQueries({ queryKey: ['campaigns'] });
      await qc.invalidateQueries({ queryKey: ['campaigns', c.campaign_id] });
      opts?.onSuccess?.(c);
    },
    onError: (err) => opts?.onError?.(err as Error),
  });
}
