// 26 IX-14 — the ONE conformance-staleness consumer hook. Fetches the book-keyed read contract
// and derives the set the scene surfaces need: a chapter is "dirty" (canon moved since the last
// conformance run) when it is in some DIRTY arc's `stale_chapters` (spec 26 §debugger — a scene's
// dirty chip = its arc's `dirty ∧ chapter ∈ stale_chapters`). Advisory + cheap; re-fetch on focus,
// no cache to invalidate (a conformance run clears the badge by predicate on the next read).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { ConformanceStatus } from '@/features/composition/types';

export type ConformanceState = {
  status: ConformanceStatus | null;
  /** chapter_ids that drifted since the last conformance snapshot (union over dirty arcs). */
  dirtyChapters: Set<string>;
  /** book-level rollup — index-stale chapters (what the sweeper heals). */
  staleChapterCount: number;
  loading: boolean;
  error: string | null;
  refresh: () => void;
};

export function useConformanceStatus(bookId: string | null): ConformanceState {
  const { accessToken } = useAuth();
  const token = accessToken ?? null;
  const [status, setStatus] = useState<ConformanceStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token || !bookId) { setStatus(null); return; }
    setLoading(true); setError(null);
    try {
      setStatus(await compositionApi.getConformanceStatus(bookId, token));
    } catch (e) {
      // Advisory signal — a failure must NOT break the surface it decorates; just drop the chips.
      setStatus(null);
      setError(e instanceof Error ? e.message : 'conformance unavailable');
    } finally {
      setLoading(false);
    }
  }, [token, bookId]);

  useEffect(() => { void load(); }, [load]);

  const dirtyChapters = useMemo(() => {
    const s = new Set<string>();
    for (const arc of status?.arcs ?? []) {
      if (arc.dirty) for (const ch of arc.stale_chapters) s.add(ch);
    }
    return s;
  }, [status]);

  return {
    status, dirtyChapters,
    staleChapterCount: status?.index.stale_chapter_count ?? 0,
    loading, error, refresh: load,
  };
}
