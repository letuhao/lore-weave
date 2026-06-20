import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { tieringApi } from '@/features/glossary/tieringApi';

/**
 * Controller for the standards recycle bin — lists soft-deleted user genres & kinds
 * and restores / permanently purges them. Restoring also invalidates the live
 * standards lists so the row reappears immediately.
 */
export function useStandardsTrash(open: boolean) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const enabled = !!accessToken && open;

  const genresQ = useQuery({
    queryKey: ['standards-trash-genres'],
    queryFn: () => tieringApi.listUserGenreTrash(accessToken!),
    enabled,
  });
  const kindsQ = useQuery({
    queryKey: ['standards-trash-kinds'],
    queryFn: () => tieringApi.listUserKindTrash(accessToken!),
    enabled,
  });

  const invalidateGenres = () => {
    qc.invalidateQueries({ queryKey: ['standards-trash-genres'] });
    qc.invalidateQueries({ queryKey: ['glossary-std-genres'] });
  };
  const invalidateKinds = () => {
    qc.invalidateQueries({ queryKey: ['standards-trash-kinds'] });
    qc.invalidateQueries({ queryKey: ['glossary-std-user-kinds'] });
  };

  const restoreGenre = useMutation({
    mutationFn: (id: string) => tieringApi.restoreUserGenre(id, accessToken!),
    onSuccess: invalidateGenres,
  });
  const purgeGenre = useMutation({
    mutationFn: (id: string) => tieringApi.purgeUserGenre(id, accessToken!),
    onSuccess: invalidateGenres,
  });
  const restoreKind = useMutation({
    mutationFn: (id: string) => tieringApi.restoreUserKind(id, accessToken!),
    onSuccess: invalidateKinds,
  });
  const purgeKind = useMutation({
    mutationFn: (id: string) => tieringApi.purgeUserKind(id, accessToken!),
    onSuccess: invalidateKinds,
  });

  return {
    genres: genresQ.data ?? [],
    kinds: kindsQ.data ?? [],
    isLoading: genresQ.isLoading || kindsQ.isLoading,
    restoreGenre,
    purgeGenre,
    restoreKind,
    purgeKind,
  };
}
