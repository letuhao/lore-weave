// PlanForge Runs-list controller (D-PLANFORGE-NO-RESUME follow-up) — the Planner panel's
// list tab needs to see runs that already exist server-side (created via this session, a past
// session, or an agent calling the REST/MCP surface directly), not just what createRun() set
// in local state this mount. Same imperative style as usePlanRun.ts (no react-query dependency
// in this feature) — a plain fetch-on-mount + manual refresh.
import { useCallback, useEffect, useState } from 'react';
import { planForgeApi } from '../api';
import type { PlanRunDetail } from '../types';

export interface UsePlanRunsList {
  items: PlanRunDetail[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function usePlanRunsList(bookId: string, token: string | null): UsePlanRunsList {
  const [items, setItems] = useState<PlanRunDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gen, setGen] = useState(0);

  useEffect(() => {
    if (!token || !bookId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    planForgeApi.listRuns(bookId, token, { limit: 50 })
      .then((page) => { if (!cancelled) setItems(page.items); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [bookId, token, gen]);

  const refresh = useCallback(() => setGen((g) => g + 1), []);
  return { items, loading, error, refresh };
}
