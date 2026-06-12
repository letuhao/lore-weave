import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type { EntityRevisionSummary, EntityRevisionDetail } from '../types';

/**
 * Controller for the entity version history (D-GLOSSARY-VERSIONING, VG-3).
 *
 * Lists an entity's revisions (captured async by the VG-1 projection) and owns
 * the restore action. Restore reconciles the live entity to the chosen revision
 * (server-side, exact + id-preserving) and is itself versioned, so it is
 * reversible. After a restore the revisions query is invalidated; the editor
 * re-fetches the entity via the panel's onRestored callback.
 */
export function useEntityRevisions(bookId: string, entityId: string) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['glossary-entity-revisions', bookId, entityId],
    queryFn: () => glossaryApi.listEntityRevisions(bookId, entityId, accessToken!),
    enabled: !!accessToken && !!entityId,
  });

  const revisions: EntityRevisionSummary[] = data?.revisions ?? [];

  const restore = async (revisionId: string): Promise<void> => {
    await glossaryApi.restoreEntityRevision(bookId, entityId, revisionId, accessToken!);
    // Restore creates a NEW revision (the restored state) → refresh the list.
    void queryClient.invalidateQueries({
      queryKey: ['glossary-entity-revisions', bookId, entityId],
    });
  };

  return { revisions, isLoading, error, refetch, restore };
}

/** Fetches one revision's full snapshot on demand (the "View" affordance). */
export function useEntityRevisionDetail(
  bookId: string,
  entityId: string,
  revisionId: string | null,
) {
  const { accessToken } = useAuth();
  const { data, isLoading, error } = useQuery({
    queryKey: ['glossary-entity-revision', bookId, entityId, revisionId],
    queryFn: () => glossaryApi.getEntityRevision(bookId, entityId, revisionId!, accessToken!),
    enabled: !!accessToken && !!revisionId,
  });
  return { detail: (data ?? null) as EntityRevisionDetail | null, isLoading, error };
}
