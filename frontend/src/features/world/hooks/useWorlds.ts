import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { worldsApi } from '../api';
import type { CreateWorldPayload, World } from '../types';

// C21 — worlds browser controller (HOME list + create). Owns the list query +
// the create mutation; the view renders only. Server is the source of truth
// (no localStorage of world data).
export function useWorlds() {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['worlds'],
    queryFn: () => worldsApi.listWorlds(accessToken!),
    enabled: !!accessToken,
  });

  const createMutation = useMutation({
    mutationFn: (payload: CreateWorldPayload): Promise<World> =>
      worldsApi.createWorld(accessToken!, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['worlds'] }),
  });

  return {
    items: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error as Error | null,
    createWorld: createMutation.mutateAsync,
    isCreating: createMutation.isPending,
  };
}
