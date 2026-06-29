import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { mcpApprovalsApi, type McpApproval } from './api';

/**
 * Controller for the Settings → MCP access "pending approvals" panel (P4 / OD-2).
 * Owns the pending list + the approve/deny flows. Approvals are rare, so this polls
 * on a modest interval (not SSE). Approve can take a while (the action executes
 * server-side), so it tracks a per-row busy id.
 */
export function useMcpApprovals(pollMs = 20000) {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();
  const [approvals, setApprovals] = useState<McpApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    try {
      const data = await mcpApprovalsApi.list(accessToken, 'pending');
      setApprovals(data.items ?? []);
    } catch {
      /* the panel is supplementary — a transient list failure is silent */
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void refresh();
    if (!accessToken || pollMs <= 0) return;
    const id = setInterval(() => void refresh(), pollMs);
    return () => clearInterval(id);
  }, [refresh, accessToken, pollMs]);

  const approve = useCallback(
    async (approvalId: string) => {
      if (!accessToken || busyId) return;
      setBusyId(approvalId);
      try {
        const res = await mcpApprovalsApi.approve(accessToken, approvalId);
        if (res.status === 'reprice_required') {
          toast.error(t('mcp.approvals.toast.reprice'));
        } else {
          toast.success(t('mcp.approvals.toast.approved'));
        }
        await refresh();
      } catch (e) {
        toast.error((e as Error).message || t('mcp.approvals.toast.approve_failed'));
      } finally {
        setBusyId(null);
      }
    },
    [accessToken, busyId, refresh, t],
  );

  const deny = useCallback(
    async (approvalId: string) => {
      if (!accessToken || busyId) return;
      setBusyId(approvalId);
      try {
        await mcpApprovalsApi.deny(accessToken, approvalId);
        toast.success(t('mcp.approvals.toast.denied'));
        await refresh();
      } catch (e) {
        toast.error((e as Error).message || t('mcp.approvals.toast.deny_failed'));
      } finally {
        setBusyId(null);
      }
    },
    [accessToken, busyId, refresh, t],
  );

  return { approvals, loading, busyId, approve, deny, refresh };
}
