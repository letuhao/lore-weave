import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type { EntityKind } from '../types';

export function useEntityKinds() {
  const { accessToken } = useAuth();
  const [kinds, setKinds] = useState<EntityKind[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!accessToken) return;
    setIsLoading(true);
    glossaryApi
      .getKinds(accessToken)
      .then(setKinds)
      .catch((e: unknown) => setError((e as Error).message || 'Failed to load kinds'))
      .finally(() => setIsLoading(false));
  }, [accessToken]);

  return { kinds, isLoading, error };
}
