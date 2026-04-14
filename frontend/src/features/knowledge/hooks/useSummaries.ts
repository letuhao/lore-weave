import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi } from '../api';
import type { SummariesListResponse, SummaryUpdatePayload } from '../types';

// Single shared key — global bio + per-project summaries come from
// the same GET /v1/knowledge/summaries response. After a PATCH we
// invalidate the whole thing so any open tab (Global, project editor
// down the line) re-reads fresh state.
const QUERY_KEY = ['knowledge-summaries'] as const;

export function useSummaries() {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => knowledgeApi.listSummaries(accessToken!),
    enabled: !!accessToken,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });

  const updateGlobalMutation = useMutation({
    mutationFn: (payload: SummaryUpdatePayload) =>
      knowledgeApi.updateGlobalSummary(payload, accessToken!),
    onSuccess: invalidate,
  });

  const data = query.data as SummariesListResponse | undefined;

  return {
    global: data?.global ?? null,
    projects: data?.projects ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    updateGlobal: updateGlobalMutation.mutateAsync,
    isUpdatingGlobal: updateGlobalMutation.isPending,
  };
}
