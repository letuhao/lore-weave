// W6 §3.2 — the library list controller (react-query). Owns: the list query, the
// scope tab (my | catalog), client-side facet narrowing over the fetched page
// (the server does the heavy filter), and a debounced search. No JSX.
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motifApi, type MotifListParams } from '../api';
import type { Motif, MotifKind } from '../types';

export type LibraryScope = 'my' | 'catalog';

export type MotifFacets = {
  kind?: MotifKind;
  genre?: string;
  tension?: number;     // exact T1..T5 narrowing
  tier?: 'system' | 'user' | 'public';
};

export function useMotifLibrary(token: string | null, opts?: { initialScope?: LibraryScope }) {
  const [scope, setScope] = useState<LibraryScope>(opts?.initialScope ?? 'my');
  const [search, setSearch] = useState('');
  const [facets, setFacets] = useState<MotifFacets>({});

  // The server params: scope 'my' fetches the full read-predicate list ('all'),
  // 'catalog' fetches the public allow-list. `q` rides to the server (ILIKE).
  const params: MotifListParams = {
    scope: scope === 'catalog' ? 'public' : 'all',
    q: search.trim() || undefined,
    limit: 200,
  };

  const query = useQuery({
    queryKey: ['composition', 'motifs', scope, params.scope, params.q],
    queryFn: () => motifApi.list(params, token!),
    enabled: !!token,
    select: (d): Motif[] => d.motifs,
  });

  // Client-side facet narrowing over the fetched page (cheap; server already did
  // the scope/q filter). Derived — recomputed only when inputs change.
  const motifs = useMemo<Motif[]>(() => {
    const all = query.data ?? [];
    return all.filter((m) => {
      if (facets.kind && m.kind !== facets.kind) return false;
      if (facets.genre && !m.genre_tags.includes(facets.genre)) return false;
      if (facets.tension != null && m.tension_target !== facets.tension) return false;
      if (facets.tier) {
        const tier = m.owner_user_id == null ? 'system' : (m.visibility === 'public' ? 'public' : 'user');
        if (tier !== facets.tier) return false;
      }
      return true;
    });
  }, [query.data, facets]);

  const setFacet = <K extends keyof MotifFacets>(k: K, v: MotifFacets[K]) =>
    setFacets((prev) => ({ ...prev, [k]: prev[k] === v ? undefined : v }));
  const clearFacets = () => setFacets({});

  // The available facet values (derived from the fetched page — only show filters
  // that would actually match something).
  const available = useMemo(() => {
    const all = query.data ?? [];
    const genres = new Set<string>();
    const kinds = new Set<MotifKind>();
    for (const m of all) {
      m.genre_tags.forEach((g) => genres.add(g));
      kinds.add(m.kind);
    }
    return { genres: [...genres].sort(), kinds: [...kinds].sort() };
  }, [query.data]);

  const isEmpty = !query.isLoading && !query.isError && motifs.length === 0 && (query.data?.length ?? 0) === 0;

  return {
    motifs,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    isEmpty,
    scope, setScope,
    search, setSearch,
    facets, setFacet, clearFacets,
    available,
    rawCount: query.data?.length ?? 0,
  };
}
