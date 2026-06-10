import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { campaignsApi } from '../api';

/** List the current user's campaigns (the /campaigns landing). */
export function useCampaigns() {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['campaigns'],
    queryFn: () => campaignsApi.list(accessToken!),
    enabled: !!accessToken,
  });
}

/** One campaign + its per-chapter projection (the detail page). */
export function useCampaign(campaignId?: string) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['campaigns', campaignId],
    queryFn: () => campaignsApi.get(campaignId!, accessToken!),
    enabled: !!accessToken && !!campaignId,
  });
}
