import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi } from '../api';

// D-K8-01: history panel for the global summary bio.
// Per-project history lives in the same table but isn't exposed
// in Track 1; Track 2 can add a parallel hook + panel when needed.

const QUERY_KEY = ['knowledge-summary-versions', 'global'] as const;

export function useGlobalSummaryVersions(enabled: boolean = true) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => knowledgeApi.listGlobalSummaryVersions(accessToken!),
    // Only fetch when the panel is actually open — keeps the
    // Knowledge page's initial load cheap. The panel passes `true`
    // on mount.
    enabled: enabled && !!accessToken,
    // Stale immediately — the list is small and the user expects
    // it to reflect saves they just made in the same session.
    staleTime: 0,
  });

  const rollbackMutation = useMutation({
    mutationFn: (args: { version: number; expectedVersion: number }) =>
      knowledgeApi.rollbackGlobalSummary(
        args.version,
        accessToken!,
        args.expectedVersion,
      ),
    onSuccess: () => {
      // Rollback writes a new live row AND a new history row.
      // Invalidate both the summaries list (for the current bio)
      // AND the version list (for the panel).
      void queryClient.invalidateQueries({ queryKey: ['knowledge-summaries'] });
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });

  return {
    items: query.data?.items ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    rollback: rollbackMutation.mutateAsync,
    isRollingBack: rollbackMutation.isPending,
  };
}
