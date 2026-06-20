import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { tieringApi } from '@/features/glossary/tieringApi';

/**
 * Controller for editing a user kind's genre links (`/user-kinds/{id}/genres`).
 * Loads the kind's current genre ids and replaces the full set on save (the
 * backend validates every id is one of the caller's live user genres → 422 else).
 */
export function useKindGenres(userKindId: string | null) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const enabled = !!accessToken && !!userKindId;

  const linksQ = useQuery({
    queryKey: ['standards-kind-genres', userKindId],
    queryFn: () => tieringApi.listUserKindGenres(userKindId!, accessToken!),
    enabled,
  });

  const save = useMutation({
    mutationFn: (genreIds: string[]) => tieringApi.setUserKindGenres(userKindId!, genreIds, accessToken!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['standards-kind-genres', userKindId] }),
  });

  return {
    linkedGenreIds: (linksQ.data ?? []).map((l) => l.genre_id),
    isLoading: linksQ.isLoading,
    error: linksQ.error,
    save,
  };
}
