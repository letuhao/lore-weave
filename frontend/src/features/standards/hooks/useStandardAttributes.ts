import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { tieringApi } from '@/features/glossary/tieringApi';
import type { Attribute, UserAttributeCreate } from '@/features/glossary/tieringTypes';

/**
 * Controller for the Attributes tab — scoped to a (user-kind × user-genre) pair.
 * Lists the caller's user attributes for the pair + the SYSTEM attributes of the
 * pair's system parents (read-only reference, when both were cloned from system).
 * Create attaches by-code (the backend 422s if kind/genre aren't the caller's live
 * user rows — G2 AttachByCodeAndTenancy). Edit/delete land in M3.
 */
export function useStandardAttributes(params: {
  userKindId: string | null;
  userGenreId: string | null;
  systemKindId?: string | null;
  systemGenreId?: string | null;
}) {
  const { userKindId, userGenreId, systemKindId, systemGenreId } = params;
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const ready = !!accessToken && !!userKindId && !!userGenreId;

  const userAttrsQ = useQuery({
    queryKey: ['standards-user-attrs', userKindId, userGenreId],
    queryFn: () =>
      tieringApi.listUserAttributes(accessToken!, { kindId: userKindId!, genreId: userGenreId! }),
    enabled: ready,
  });

  const hasSystemParent = !!systemKindId && !!systemGenreId;
  const systemAttrsQ = useQuery({
    queryKey: ['standards-system-attrs', systemKindId, systemGenreId],
    queryFn: () => tieringApi.listSystemAttributes(systemKindId!, systemGenreId!, accessToken!),
    enabled: !!accessToken && hasSystemParent,
  });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ['standards-user-attrs', userKindId, userGenreId] });

  const createAttr = useMutation({
    mutationFn: (payload: UserAttributeCreate) => tieringApi.createUserAttribute(payload, accessToken!),
    onSuccess: invalidate,
  });

  return {
    userAttrs: (userAttrsQ.data ?? []) as Attribute[],
    systemAttrs: (systemAttrsQ.data ?? []) as Attribute[],
    hasSystemParent,
    isLoading: userAttrsQ.isLoading,
    error: userAttrsQ.error,
    createAttr,
    invalidate,
  };
}
