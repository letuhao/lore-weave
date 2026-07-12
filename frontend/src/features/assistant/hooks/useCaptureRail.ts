// WS-1.10 controller — the "today so far" rail. Reads the diary book's glossary entities (the
// People / Projects the capture pipeline wrote as the user talked). CLAUDE.md MVC: this hook owns
// the fetch + state; the CaptureRail view only renders what it returns.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { defaultFilters, type GlossaryEntitySummary } from '@/features/glossary/types';

export function useCaptureRail(bookId: string | null) {
  const { accessToken } = useAuth();
  const [entities, setEntities] = useState<GlossaryEntitySummary[]>([]);
  const [loading, setLoading] = useState(false);
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
    try {
      const res = await glossaryApi.listEntities(
        bookId,
        { ...defaultFilters, status: 'active', limit: 50, sort: 'updated_at' },
        accessToken,
      );
      if (mounted.current) setEntities(res.items);
    } catch {
      // A rail read failure is non-fatal — the capture still happened server-side; the home
      // strip just shows the last-known set. Never blocks the chat.
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [accessToken, bookId]);

  // SYNC: load the rail once the diary book id is known (and whenever it changes).
  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { entities, loading, refresh };
}
