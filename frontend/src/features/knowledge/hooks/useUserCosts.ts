import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type UserCostSummary } from '../api';

// K19b.6 — user-wide AI spending + budget card hook.
//
// Calm staleness: production `current_month_spent_usd` only changes
// when the extraction worker records spend (D-K16.11-01 still open,
// so today it stays at 0). A 60s staleTime dedupes concurrent
// readers (tab nav, BuildGraphDialog open) without active polling.
// Callers that mutate the budget should `useQueryClient` and
// invalidate `['knowledge-costs', userId]` to refresh immediately.

export interface UseUserCostsResult {
  costs: UserCostSummary | null;
  isLoading: boolean;
  error: Error | null;
}

export function useUserCosts(): UseUserCostsResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: ['knowledge-costs', userId] as const,
    queryFn: () => knowledgeApi.getUserCosts(accessToken!),
    enabled: !!accessToken,
    staleTime: 60_000,
  });

  return {
    costs: query.data ?? null,
    isLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
  };
}
