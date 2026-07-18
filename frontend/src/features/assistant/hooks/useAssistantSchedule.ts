// A3 (arm the autonomous layer) — the controller for the "let the assistant work on its own" settings.
// The autonomous jobs (auto end-of-day distill, weekly rollup/reflection, proactive check-ins, reminders)
// were built + wired scheduler→worker but DORMANT: nothing ever created a `scheduled_agent_runs` row, so
// they never fired. This hook is the missing arm: it READS effective per-job state (server is SoT — the
// scheduler rows) and WRITES the opt-in. Fail-closed by construction — a job with no row reads OFF, and
// enabling spends background tokens so it is never on by default (Settings-and-Config + spend-fails-closed).
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';
import type { AutonomousJobKind, ScheduleRow } from '../types';

export function useAssistantSchedule() {
  const { accessToken } = useAuth();
  const [rows, setRows] = useState<ScheduleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingKind, setSavingKind] = useState<AutonomousJobKind | null>(null);
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
      const res = await assistantApi.getSchedule(accessToken);
      if (mounted.current) setRows(res.schedules ?? []);
    } catch {
      // A read failure leaves the toggles at their fail-closed default (OFF) rather than guessing ON.
      if (mounted.current) setRows([]);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Effective state — the whole point of the Settings-and-Config rule: read the real value, never assume.
  // A job_kind with no server row is OFF (fail-closed).
  const isEnabled = useCallback(
    (kind: AutonomousJobKind) => rows.find((r) => r.job_kind === kind)?.enabled === true,
    [rows],
  );
  const nextFireAt = useCallback(
    (kind: AutonomousJobKind) => rows.find((r) => r.job_kind === kind)?.next_fire_at ?? null,
    [rows],
  );

  const setEnabled = useCallback(
    async (kind: AutonomousJobKind, enabled: boolean, timezone?: string) => {
      if (!accessToken) return false;
      setSavingKind(kind);
      try {
        await assistantApi.setSchedule(accessToken, { job_kind: kind, enabled, timezone });
        await refresh(); // re-read the server truth (never optimistically trust the local flip)
        toast.success(enabled ? 'The assistant will do this on its own now.' : 'Turned off — nothing runs on its own.');
        return true;
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Could not save the setting.');
        return false;
      } finally {
        if (mounted.current) setSavingKind(null);
      }
    },
    [accessToken, refresh],
  );

  return { rows, loading, savingKind, isEnabled, nextFireAt, setEnabled, refresh };
}
