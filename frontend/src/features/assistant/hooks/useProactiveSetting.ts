// D-A3-PROACTIVE-SETTING — the "Proactive check-ins" controller. Proactive is DOUBLE-GATED: the chat
// proactive-turn seam fails closed on `assistant.proactive_enabled` (the opt-in gate), AND the scheduler
// only fires it when a `proactive_nudge` schedule row is armed. A toggle that set only one would silently
// no-op (the reason A3 didn't expose it). So this hook drives BOTH together, and reads the gate as the
// effective state. Fail-closed: no gate ⇒ OFF; enabling spends background tokens, so never on by default.
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';

export function useProactiveSetting() {
  const { accessToken } = useAuth();
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    try {
      const prefs = await assistantApi.getAiPrefs(accessToken);
      if (mounted.current) setEnabled(prefs.assistant?.proactive_enabled === true); // fail-closed
    } catch {
      if (mounted.current) setEnabled(false);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setProactive = useCallback(
    async (on: boolean, timezone?: string) => {
      if (!accessToken) return false;
      setSaving(true);
      try {
        // BOTH gates, kept in sync: the chat opt-in AND the scheduler trigger. The ORDER matters for a
        // partial cross-service failure — `proactive_enabled` (the gate the seam checks, and the effective
        // state we read back) must be the LAST thing set on ENABLE and the FIRST on DISABLE, so a failure
        // of the other write can never leave the gate ON with no trigger (a silent no-op) or spending.
        if (on) {
          await assistantApi.setSchedule(accessToken, { job_kind: 'proactive_nudge', enabled: true, timezone });
          await assistantApi.setProactiveEnabled(accessToken, true);
        } else {
          await assistantApi.setProactiveEnabled(accessToken, false);
          await assistantApi.setSchedule(accessToken, { job_kind: 'proactive_nudge', enabled: false, timezone });
        }
        await refresh();
        toast.success(on ? 'Proactive check-ins on — I may reach out when it has been a while.' : 'Proactive check-ins off.');
        return true;
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Could not save the setting.');
        return false;
      } finally {
        if (mounted.current) setSaving(false);
      }
    },
    [accessToken, refresh],
  );

  return { enabled, loading, saving, setProactive, refresh };
}
