import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';

/** The book's glossary entity names (lightweight) for the Compose existing-target
 *  autocomplete (D-COMPOSE-EXISTING-PICKER). Best-effort — returns [] until loaded
 *  / on no auth / on error; the picker then degrades to a free-text name field
 *  (correctness — the entity's covered dims — is handled server-side, not here).
 *  Reuses the glossary feature's read (same cross-feature pattern as useUserModels). */
export function useBookEntities(bookId: string) {
  const { accessToken } = useAuth();
  const { data } = useQuery({
    queryKey: ['glossary-entity-names', bookId],
    queryFn: () => glossaryApi.listEntityNames(bookId, accessToken!),
    enabled: !!accessToken && !!bookId,
  });
  return data ?? [];
}
