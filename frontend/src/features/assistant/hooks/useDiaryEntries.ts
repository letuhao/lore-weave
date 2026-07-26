// M1 (mobile) controller — the journal timeline. Reads the diary book's distilled entries
// (newest-first) for the mobile Journal sheet. CLAUDE.md MVC: the hook owns the fetch +
// state; the view only renders what it returns. Pure reuse of the existing
// assistantApi.listDiaryEntries endpoint (WS-1.10) — no new BE.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';
import type { DiaryEntry } from '../types';

export function useDiaryEntries(bookId: string | null) {
  const { accessToken } = useAuth();
  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!accessToken || !bookId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await assistantApi.listDiaryEntries(accessToken, bookId);
      // Show the human-facing PRIMARY entries only; newest first (the API already orders,
      // but sort defensively so the timeline is stable regardless of server order).
      const primary = res.entries
        .filter((e) => e.journal_kind === 'primary')
        // newest-first; localeCompare returns 0 for equal dates (stable, valid comparator).
        .sort((a, b) => b.entry_date.localeCompare(a.entry_date));
      if (mounted.current) setEntries(primary);
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : 'Could not load your journal.');
      }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [accessToken, bookId]);

  // SYNC: load once the diary book id is known (and whenever it changes).
  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { entries, loading, error, refresh };
}
