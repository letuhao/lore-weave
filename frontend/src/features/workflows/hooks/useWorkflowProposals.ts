// Controller hook (MVC) — the workflow-proposals inbox: list + approve + reject.
// Mirrors extensions' useProposals (the skill-proposal spine); the routes it drives
// (GET /workflow-proposals, PUT …/approve, POST …/reject) already ship. Approving here
// is what closes the "an agent proposes a workflow no human can approve" hole (S-12).
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { workflowsApi } from '../api';
import type { WorkflowProposal } from '../types';

export function useWorkflowProposals() {
  const { accessToken } = useAuth();
  const [proposals, setProposals] = useState<WorkflowProposal[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState('pending');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await workflowsApi.listProposals(accessToken, { status, limit: 50 });
      setProposals(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load workflow proposals');
    } finally {
      setLoading(false);
    }
  }, [accessToken, status]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const approve = useCallback(
    async (p: WorkflowProposal) => {
      if (!accessToken) return;
      await workflowsApi.approveProposal(accessToken, p.proposal_id);
      await refresh();
    },
    [accessToken, refresh],
  );

  const reject = useCallback(
    async (p: WorkflowProposal, reason = '') => {
      if (!accessToken) return;
      await workflowsApi.rejectProposal(accessToken, p.proposal_id, reason);
      await refresh();
    },
    [accessToken, refresh],
  );

  return { proposals, total, status, setStatus, loading, error, refresh, approve, reject };
}
