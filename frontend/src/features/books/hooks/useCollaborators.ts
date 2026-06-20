import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi, type Collaborator, type CollaboratorRole } from '@/features/books/api';

type ApiError = Error & { status?: number; code?: string };

/**
 * E0-5 collaborators controller. Owns the list + the invite/change-role/remove
 * actions for one book. Self-gating: the underlying endpoints are owner-only, so a
 * 403/404 on load sets `forbidden` (the panel renders nothing for a non-owner —
 * the Sharing tab is shown to collaborators too). All mutations refetch the list so
 * the caller stays a pure view.
 */
export function useCollaborators(bookId: string) {
  const { accessToken } = useAuth();
  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const { collaborators } = await booksApi.listCollaborators(accessToken, bookId);
      setCollaborators(collaborators);
      setForbidden(false);
    } catch (e) {
      const err = e as ApiError;
      // Owner-only: a non-owner (403) or unknown book (404) → hide the panel.
      if (err.status === 403 || err.status === 404) setForbidden(true);
      else setError(err.message || 'Failed to load collaborators');
    } finally {
      setLoading(false);
    }
  }, [accessToken, bookId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const invite = useCallback(
    async (email: string, role: CollaboratorRole) => {
      if (!accessToken) return;
      await booksApi.inviteCollaborator(accessToken, bookId, { email, role });
      await reload();
    },
    [accessToken, bookId, reload],
  );

  const changeRole = useCallback(
    async (userId: string, role: CollaboratorRole) => {
      if (!accessToken) return;
      await booksApi.changeCollaboratorRole(accessToken, bookId, userId, role);
      await reload();
    },
    [accessToken, bookId, reload],
  );

  const remove = useCallback(
    async (userId: string) => {
      if (!accessToken) return;
      await booksApi.removeCollaborator(accessToken, bookId, userId);
      await reload();
    },
    [accessToken, bookId, reload],
  );

  return { collaborators, loading, forbidden, error, invite, changeRole, remove, reload };
}
