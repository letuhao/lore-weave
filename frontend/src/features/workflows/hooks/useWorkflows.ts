// Controller for the workflow rack (M5): owns fetch + state; the component only renders.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { workflowsApi } from '../api';
import type { WorkflowMeta } from '../types';

export interface UseWorkflows {
  workflows: WorkflowMeta[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

/** Load the workflows visible to the user (optionally scoped to a book). */
export function useWorkflows(bookId?: string): UseWorkflows {
  const { accessToken } = useAuth();
  const [workflows, setWorkflows] = useState<WorkflowMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await workflowsApi.list(accessToken, bookId ? { book_id: bookId } : {});
      setWorkflows(res.workflows ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load workflows');
    } finally {
      setLoading(false);
    }
  }, [accessToken, bookId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { workflows, loading, error, refresh };
}
