import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { campaignsApi } from '../api';
import { ACTIVE_STATUSES, type CampaignStatus } from '../types';

/** List the current user's campaigns (the /campaigns landing). */
export function useCampaigns() {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['campaigns'],
    queryFn: () => campaignsApi.list(accessToken!),
    enabled: !!accessToken,
  });
}

/** One campaign + its per-chapter projection (the chapter table; S6 polls it on a
 *  SLOW interval — the heavy chapters[] payload — while the lightweight progress
 *  query drives the live bars). */
export function useCampaign(campaignId?: string, slowPoll = false) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['campaigns', campaignId],
    queryFn: () => campaignsApi.get(campaignId!, accessToken!),
    enabled: !!accessToken && !!campaignId,
    refetchInterval: slowPoll
      ? (q) => (isActive(q.state.data?.status) ? 15000 : false)
      : undefined,
  });
}

/** S6 — lightweight progress poll (per-stage counts). Polls every 6s while the
 *  campaign is active (running/cancelling), stops on a terminal status. */
export function useCampaignProgress(campaignId?: string) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['campaign-progress', campaignId],
    queryFn: () => campaignsApi.progress(campaignId!, accessToken!),
    enabled: !!accessToken && !!campaignId,
    refetchInterval: (q) => (isActive(q.state.data?.status) ? 6000 : false),
  });
}

function isActive(status?: CampaignStatus): boolean {
  return !!status && ACTIVE_STATUSES.includes(status);
}
