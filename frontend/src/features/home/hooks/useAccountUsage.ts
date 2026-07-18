// M3 controller — the 7-day usage summary for the You screen. Reuses the existing usage API
// (no new BE). CLAUDE.md MVC: logic here, the YouPage view only renders.
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { usageApi } from '@/features/usage/api';

export function useAccountUsage() {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['account-usage', '7d'],
    queryFn: () => usageApi.getSummary(accessToken as string, 'last_7d'),
    enabled: !!accessToken,
    staleTime: 60_000,
  });
}
