import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { ontologyApi } from '../api/ontology';
import type { GraphView, ViewCreate } from '../types/ontology';

// ─────────────────────────────────────────────────────────────────────────────
// useGraphViews — controller for per-user view CRUD over a project graph.
// Views are READ-only lenses ({edge_type_codes[], node_kind_codes[]}); create /
// upsert-by-code / delete are owner-scoped. Every mutation invalidates the list.
// The ViewBuilder view owns its draft selection state locally and calls these.
// ─────────────────────────────────────────────────────────────────────────────

export function useGraphViews(projectId: string) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['kg-views', projectId],
    queryFn: () => ontologyApi.listViews(projectId, accessToken!),
    enabled: !!accessToken && !!projectId,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['kg-views', projectId] });

  const create = useMutation({
    mutationFn: (body: ViewCreate) =>
      ontologyApi.createView(projectId, body, accessToken!),
    onSuccess: invalidate,
  });

  const upsert = useMutation({
    mutationFn: (args: { code: string; body: ViewCreate }) =>
      ontologyApi.upsertView(projectId, args.code, args.body, accessToken!),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (code: string) =>
      ontologyApi.deleteView(projectId, code, accessToken!),
    onSuccess: invalidate,
  });

  return {
    views: (query.data?.items ?? []) as GraphView[],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    createView: create.mutateAsync,
    upsertView: upsert.mutateAsync,
    deleteView: remove.mutateAsync,
    isMutating: create.isPending || upsert.isPending || remove.isPending,
  };
}
