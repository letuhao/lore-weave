// DF6 controller — "What I know": the diary book's REMEMBERED (active) entities — the people,
// projects and things the assistant has kept. Reuses the glossary read (like useCaptureRail, but
// active not draft) with an optional search filter (the "ask your own memory" recall). CLAUDE.md
// MVC: fetch + state here, the view only renders. No new BE.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { defaultFilters, type GlossaryEntitySummary } from '@/features/glossary/types';

export function useMemoryEntities(bookId: string | null) {
  const { accessToken } = useAuth();
  const [entities, setEntities] = useState<GlossaryEntitySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (q: string) => {
      if (!accessToken || !bookId) return;
      setLoading(true);
      setError(null);
      try {
        const res = await glossaryApi.listEntities(
          bookId,
          { ...defaultFilters, status: 'active', limit: 200, sort: 'updated_at', searchQuery: q },
          accessToken,
        );
        if (mounted.current) setEntities(res.items);
      } catch (e) {
        if (mounted.current) setError(e instanceof Error ? e.message : 'Could not load your memory.');
      } finally {
        if (mounted.current) setLoading(false);
      }
    },
    [accessToken, bookId],
  );

  // Load once the book id is known; reload (debounced) as the search text changes.
  useEffect(() => {
    const t = setTimeout(() => void load(search), search ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, search]);

  return { entities, loading, error, search, setSearch, refresh: () => load(search) };
}
