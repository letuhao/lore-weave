// Controller hook (MVC) — workflow management: list (with workflow_id + effective
// enabled) + enable/disable + delete. Mirrors extensions' useSkills. The list is the
// same GET /workflows the rack uses; enable/disable + delete are the S-12 routes.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { workflowsApi } from '../api';
import type { WorkflowMeta } from '../types';

export function useWorkflowManage(bookId?: string) {
  const { accessToken } = useAuth();
  const [workflows, setWorkflows] = useState<WorkflowMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await workflowsApi.list(accessToken, { book_id: bookId });
      setWorkflows(res.workflows);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load workflows');
    } finally {
      setLoading(false);
    }
  }, [accessToken, bookId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const toggle = useCallback(
    async (wf: WorkflowMeta, enabled: boolean) => {
      if (!accessToken || !wf.workflow_id) return;
      await workflowsApi.setEnabled(accessToken, wf.workflow_id, enabled);
      // Optimistic local flip so the switch reflects immediately (no full refetch).
      setWorkflows((prev) => prev.map((w) => (w.workflow_id === wf.workflow_id ? { ...w, enabled } : w)));
    },
    [accessToken],
  );

  const remove = useCallback(
    async (wf: WorkflowMeta) => {
      if (!accessToken || !wf.workflow_id) return;
      await workflowsApi.remove(accessToken, wf.workflow_id);
      await refresh();
    },
    [accessToken, refresh],
  );

  return { workflows, loading, error, refresh, toggle, remove };
}
