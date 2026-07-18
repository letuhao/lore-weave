import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';

// #11 — fetch the glossary entity a KG entity is anchored to (glossary_entity_id),
// so the KG entity detail can show its authored description. Read-only; only runs
// when the KG entity is anchored AND we know the book. The glossary entity is the
// SSOT for authored prose (KG entities carry no description field of their own).
export function useAnchoredGlossaryEntity(
  bookId: string | null,
  glossaryEntityId: string | null | undefined,
) {
  const { accessToken } = useAuth();
  const enabled = !!accessToken && !!bookId && !!glossaryEntityId;
  const query = useQuery({
    queryKey: ['kg-anchored-glossary-entity', bookId, glossaryEntityId],
    queryFn: () => glossaryApi.getEntity(bookId!, glossaryEntityId!, accessToken!),
    enabled,
  });
  return {
    shortDescription: query.data?.short_description ?? null,
    scopeLabel: query.data?.scope_label ?? null,
    isLoading: enabled && query.isLoading,
  };
}
