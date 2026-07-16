// DF4 controller — the You screen's month budget + workspace count. Reuses the existing usage
// guardrail (monthly spent/limit, one call) + the books list total. No new BE. CLAUDE.md MVC.
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { usageApi } from '@/features/usage/api';
import { booksApi } from '@/features/books/api';

export function useAccountBudget() {
  const { accessToken } = useAuth();

  const guardrail = useQuery({
    queryKey: ['account-guardrail'],
    queryFn: () => usageApi.getGuardrail(accessToken as string),
    enabled: !!accessToken,
    staleTime: 60_000,
  });
  const books = useQuery({
    queryKey: ['workspace-book-count'],
    queryFn: () => booksApi.listBooks(accessToken as string, { limit: 1 }),
    enabled: !!accessToken,
    staleTime: 60_000,
  });

  return {
    spent: guardrail.data?.monthly_spent_usd ?? 0,
    limit: guardrail.data?.monthly_limit_usd ?? 0,
    bookCount: books.data?.total ?? 0,
    isLoading: guardrail.isLoading,
    error: guardrail.error as Error | null,
  };
}
