// PlanForge Runs-list controller (D-PLANFORGE-NO-RESUME follow-up) — the Planner panel's
// list tab needs to see runs that already exist server-side (created via this session, a past
// session, or an agent calling the REST/MCP surface directly), not just what createRun() set
// in local state this mount. Same imperative style as usePlanRun.ts (no react-query dependency
// in this feature) — a plain fetch-on-mount + manual refresh.
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { planForgeApi } from '../api';
import type { PlanRunDetail } from '../types';

export interface UsePlanRunsList {
  items: PlanRunDetail[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
  showArchived: boolean;
  setShowArchived: (v: boolean) => void;
  /** BE-4 — soft-archive / restore a run; refreshes the list, surfaces a 409-in-flight. */
  archive: (runId: string) => Promise<void>;
  restore: (runId: string) => Promise<void>;
}

export function usePlanRunsList(bookId: string, token: string | null): UsePlanRunsList {
  const [items, setItems] = useState<PlanRunDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gen, setGen] = useState(0);
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    if (!token || !bookId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    planForgeApi.listRuns(bookId, token, { limit: 50, includeArchived: showArchived })
      .then((page) => { if (!cancelled) setItems(page.items); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [bookId, token, gen, showArchived]);

  const refresh = useCallback(() => setGen((g) => g + 1), []);

  const archive = useCallback(async (runId: string) => {
    if (!token) return;
    setError(null);
    try {
      await planForgeApi.archiveRun(bookId, runId, token);
      setGen((g) => g + 1);
      // F-3 — archive is destructive-ish; give an immediate Undo (mirrors canon-rule archive)
      // instead of forcing the author to hunt the "Show archived" toggle to recover a mis-click.
      toast('Run archived', {
        action: {
          label: 'Undo',
          onClick: () => {
            void planForgeApi.restoreRun(bookId, runId, token).then(() => setGen((g) => g + 1));
          },
        },
      });
    } catch (e) {
      // 409 PLAN_RUN_JOB_IN_FLIGHT — surface it; a run mid-compile can't be archived.
      const err = e as { body?: { detail?: { code?: string } }; message?: string };
      setError(err?.body?.detail?.code === 'PLAN_RUN_JOB_IN_FLIGHT'
        ? 'Cannot archive — this run has a job in flight.'
        : (e as Error).message);
    }
  }, [bookId, token]);

  const restore = useCallback(async (runId: string) => {
    if (!token) return;
    setError(null);
    try {
      await planForgeApi.restoreRun(bookId, runId, token);
      setGen((g) => g + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [bookId, token]);

  return { items, loading, error, refresh, showArchived, setShowArchived, archive, restore };
}
