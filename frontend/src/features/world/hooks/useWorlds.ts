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

  // P3 — delete. 🔴 D-S07's GUARD LIVES HERE, not only in the dialog's disabled prop.
  // `books.world_id` is ON DELETE SET NULL, so the REST route SILENTLY ORPHANS member books;
  // the MCP tool refuses while a world still holds any, and a UI that skipped that check would
  // re-open the exact footgun the tool was hardened against. A `disabled` button is a hint, not
  // a guarantee — the mutation itself refuses.
  const deleteMutation = useMutation({
    mutationFn: async (world: World): Promise<void> => {
      if (world.book_count > 0) {
        throw new Error(
          `"${world.name}" still holds ${world.book_count} book(s). Move them out first — ` +
          'deleting the world would detach them rather than delete them.',
        );
      }
      return worldsApi.deleteWorld(accessToken!, world.world_id);
    },
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
    deleteWorld: deleteMutation.mutateAsync,
    isDeleting: deleteMutation.isPending,
  };
}
