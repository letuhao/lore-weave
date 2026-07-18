// Controller for the binding settings (M6): owns load + the veto/enable write; component renders.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { modeBindingsApi } from '../api';
import { MODES, type Mode, type ModeBinding } from '../types';

export interface UseModeBindings {
  bindings: Record<Mode, ModeBinding | null>;
  loading: boolean;
  error: string | null;
  busyMode: Mode | null;
  refresh: () => Promise<void>;
  /** Disable (veto) or re-enable a workflow for a mode, at the USER tier. Consumed-by-effect:
   *  a disabled workflow drops out of the effective inject_workflows. */
  setWorkflowDisabled: (mode: Mode, slug: string, disabled: boolean) => Promise<void>;
}

const EMPTY: Record<Mode, ModeBinding | null> = { ask: null, write: null, plan: null };

export function useModeBindings(bookId?: string): UseModeBindings {
  const { accessToken } = useAuth();
  const [bindings, setBindings] = useState<Record<Mode, ModeBinding | null>>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyMode, setBusyMode] = useState<Mode | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.all(MODES.map((m) => modeBindingsApi.get(accessToken, m, bookId)));
      setBindings({ ask: results[0], write: results[1], plan: results[2] });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load bindings');
    } finally {
      setLoading(false);
    }
  }, [accessToken, bookId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setWorkflowDisabled = useCallback(
    async (mode: Mode, slug: string, disabled: boolean) => {
      if (!accessToken) return;
      const current = bindings[mode];
      // The PUT upserts the ENTIRE user tier, so we must echo back the user tier's OTHER fields or
      // they would be wiped. Read them from sources.user (the user's own stored contribution), not
      // from the effective binding (which is the System+user union).
      const userRow = current?.sources?.user;
      const nextDisabled = new Set(userRow?.disable_workflows ?? []);
      if (disabled) nextDisabled.add(slug);
      else nextDisabled.delete(slug);
      setBusyMode(mode);
      setError(null);
      try {
        await modeBindingsApi.put(accessToken, mode, {
          inject_skills: userRow?.inject_skills ?? [],
          inject_workflows: userRow?.inject_workflows ?? [],
          seed_tool_categories: userRow?.seed_tool_categories ?? [],
          disable_workflows: [...nextDisabled],
        }, bookId);
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to update binding');
      } finally {
        setBusyMode(null);
      }
    },
    [accessToken, bindings, bookId, refresh],
  );

  return { bindings, loading, error, busyMode, refresh, setWorkflowDisabled };
}
