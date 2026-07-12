// Controller hook (MVC) — owns the tool-consent list + the grant/revoke/deny actions.
// No JSX. Track C WS-3 (D-C-ALLOWLIST-WRITE-ONLY).
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { extensionsApi } from '../api';
import type { ApprovalKind, ToolDecision, ToolPermission } from '../types';

export function useToolPermissions() {
  const { accessToken } = useAuth();
  const [permissions, setPermissions] = useState<ToolPermission[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyKeys, setBusyKeys] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  // Monotonic guard. Two writes in quick succession fire two GETs; without this, a
  // SLOWER earlier response can land last and repaint the list with a decision the user
  // has already changed — and on a consent screen a stale row is a lie about what the
  // agent is allowed to do. Only the newest read may write state.
  const seq = useRef(0);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    const mine = ++seq.current;
    setLoading(true);
    try {
      const res = await extensionsApi.listToolPermissions(accessToken);
      if (mine !== seq.current) return; // superseded — drop it
      setPermissions(res.permissions ?? []);
    } catch (e) {
      if (mine !== seq.current) return;
      setError(e instanceof Error ? e.message : 'failed to load tool permissions');
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Always re-read from the server after a write. The list is the user's ONLY view of
  // what an autonomous agent may do on their behalf, so it must reflect what the server
  // actually stored — never what we hoped it stored.
  //
  // NOTE `refresh` deliberately does NOT clear `error`: a second, successful mutation's
  // resync would otherwise wipe the banner belonging to a FAILED one, turning a failed
  // consent change into a silent no-op. The error is cleared here, once, by the write
  // that owns it.
  const mutate = useCallback(
    async (fn: () => Promise<unknown>, key: string) => {
      if (!accessToken) return;
      setBusyKeys((s) => new Set(s).add(key));
      setError(null);
      try {
        await fn();
        await refresh();
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'the change did not save';
        // Resync FIRST, then report: the row must never show a state the server rejected.
        await refresh();
        setError(msg);
      } finally {
        setBusyKeys((s) => {
          const next = new Set(s);
          next.delete(key);
          return next;
        });
      }
    },
    [accessToken, refresh],
  );

  const revoke = useCallback(
    (p: ToolPermission) =>
      mutate(
        () => extensionsApi.revokeToolPermission(accessToken!, p.tool_name, p.kind),
        `${p.kind}:${p.tool_name}`,
      ),
    [accessToken, mutate],
  );

  const setDecision = useCallback(
    (toolName: string, kind: ApprovalKind, decision: ToolDecision) =>
      mutate(
        () => extensionsApi.setToolPermission(accessToken!, toolName, kind, decision),
        `${kind}:${toolName}`,
      ),
    [accessToken, mutate],
  );

  const isBusy = useCallback((key: string) => busyKeys.has(key), [busyKeys]);

  const allowed = permissions.filter((p) => p.decision === 'allow');
  const denied = permissions.filter((p) => p.decision === 'deny');

  return { permissions, allowed, denied, loading, isBusy, error, refresh, revoke, setDecision };
}
