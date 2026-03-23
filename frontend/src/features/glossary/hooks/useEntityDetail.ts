import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type { GlossaryEntity } from '../types';

type State = {
  entity: GlossaryEntity | null;
  isLoading: boolean;
  isSaving: boolean;
  error: string;
};

type Actions = {
  patch: (changes: { status?: string; tags?: string[] }) => Promise<void>;
  refetch: () => void;
};

export function useEntityDetail(
  bookId: string,
  entityId: string | null,
): State & Actions {
  const { accessToken } = useAuth();
  const [entity, setEntity] = useState<GlossaryEntity | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [fetchKey, setFetchKey] = useState(0);

  useEffect(() => {
    if (!entityId || !accessToken) {
      setEntity(null);
      return;
    }
    setIsLoading(true);
    setError('');
    glossaryApi
      .getEntity(bookId, entityId, accessToken)
      .then(setEntity)
      .catch((e: unknown) => setError((e as Error).message || 'Failed to load entity'))
      .finally(() => setIsLoading(false));
  }, [bookId, entityId, accessToken, fetchKey]);

  const patch = useCallback(
    async (changes: { status?: string; tags?: string[] }) => {
      if (!entity || !accessToken) return;
      setIsSaving(true);
      try {
        const updated = await glossaryApi.patchEntity(bookId, entity.entity_id, changes, accessToken);
        setEntity(updated);
      } catch (e: unknown) {
        setError((e as Error).message || 'Save failed');
      } finally {
        setIsSaving(false);
      }
    },
    [bookId, entity, accessToken],
  );

  function refetch() {
    setFetchKey((k) => k + 1);
  }

  return { entity, isLoading, isSaving, error, patch, refetch };
}
